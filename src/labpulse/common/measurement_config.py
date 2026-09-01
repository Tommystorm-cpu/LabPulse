"""Validate physical and Home Assistant-calculated measurement settings."""

import ast
from collections.abc import Mapping
from dataclasses import dataclass
import keyword
import math
import re

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from labpulse.common.identity import slug, title


_BINARY_OPERATORS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
}
_UNARY_OPERATORS: dict[type[ast.unaryop], str] = {ast.UAdd: "+", ast.USub: "-"}


@dataclass(frozen=True)
class CompiledFormula:
    """One validated expression and every runtime divisor it contains."""

    expression: str
    names: frozenset[str]
    divisors: tuple[str, ...]


def compile_formula(formula: str, allowed_names: set[str]) -> CompiledFormula:
    """Compile restricted arithmetic into Home Assistant-safe syntax."""

    if not formula.strip():
        raise ValueError("formula must not be blank")
    if len(formula) > 500:
        raise ValueError("formula must be at most 500 characters")

    # Parse the formula as Python syntax without executing it. Walking the
    # resulting tree lets LabPulse accept arithmetic while rejecting function
    # calls, attribute access, indexing, and every other Python operation.
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as error:
        raise ValueError(f"formula is not valid arithmetic: {error.msg}") from error
    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError("formula is too complex")

    names: set[str] = set()
    divisors: list[str] = []

    def render(node: ast.AST) -> str:
        """Translate one permitted syntax-tree node back into arithmetic."""

        if isinstance(node, ast.Expression):
            return render(node.body)
        if isinstance(node, ast.Name):
            if node.id not in allowed_names:
                raise ValueError(f"formula uses unknown name: {node.id}")
            names.add(node.id)
            return node.id
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("formula constants must be finite numbers")
            if not math.isfinite(float(node.value)):
                raise ValueError("formula constants must be finite numbers")
            return repr(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return f"({_UNARY_OPERATORS[type(node.op)]}{render(node.operand)})"
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = render(node.left)
            right = render(node.right)
            if isinstance(node.op, ast.Div):
                # Home Assistant checks these expressions for zero before it
                # evaluates the complete custom measurement.
                divisors.append(right)
            return f"({left} {_BINARY_OPERATORS[type(node.op)]} {right})"
        raise ValueError("formula may only use names, numbers, parentheses, +, -, *, and /")

    expression = render(tree)
    return CompiledFormula(expression, frozenset(names), tuple(divisors))


def validate_setup_id(setup_id: str) -> str:
    """Return one valid stable setup identifier."""

    normalized = setup_id.strip()
    if not normalized or slug(normalized) != normalized:
        raise ValueError("setup IDs must use lowercase letters, numbers, and underscores")
    return normalized


def normalize_setups(value: object) -> tuple[str, ...] | None:
    """Normalize an optional, explicit non-empty setup-ID list."""

    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError("setups must contain at least one setup ID")
        normalized_ids: list[str] = []
        for setup_id in value:
            if not isinstance(setup_id, str):
                raise ValueError("selected setup IDs must be strings")
            normalized_ids.append(validate_setup_id(setup_id))
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("selected setup IDs must be unique")
        return tuple(normalized_ids)
    raise ValueError("setups must be a non-empty list of setup IDs")


def validate_measurement_icon(icon: str | None) -> str | None:
    """Normalize an optional Material Design entity icon."""

    if icon is None:
        return None
    normalized = icon.strip()
    if re.fullmatch(r"mdi:[a-z0-9]+(?:-[a-z0-9]+)*", normalized) is None:
        raise ValueError("measurement icon must use an mdi: icon identifier")
    return normalized


class MeasurementConfig(BaseModel):
    """One named value published by a LabPulse service."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    short_label: str | None = None
    group: str | None = None
    setups: tuple[str, ...] | None = None
    alarmed: bool = Field(default=True, strict=True)
    unit: str | None = None
    device_class: str | None = None
    icon: str | None = None
    state_class: str | None = "measurement"

    @field_validator("setups", mode="before")
    @classmethod
    def validate_setups(cls, value: object) -> tuple[str, ...] | None:
        """Normalize an explicit non-empty setup-ID list."""

        return normalize_setups(value)

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, icon: str | None) -> str | None:
        """Normalize an optional Material Design entity icon."""

        return validate_measurement_icon(icon)

    def display_label(self, measurement_id: str) -> str:
        """Return the full label used outside compact dashboard rows."""

        return self.label or title(measurement_id)

    def display_short_label(self, measurement_id: str) -> str:
        """Return the shorter label used where surrounding context is sufficient."""

        return self.short_label or self.display_label(measurement_id)


class CustomMeasurementConfig(BaseModel):
    """One Home Assistant-calculated reading built from physical measurements."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    short_label: str | None = None
    group: str | None = None
    setups: tuple[str, ...]
    inputs: dict[str, str]
    constants: dict[str, float] = Field(default_factory=dict)
    formula: str
    precision: int = Field(default=2, ge=0, le=10)
    alarmed: bool = Field(default=True, strict=True)
    unit: str | None = None
    device_class: str | None = None
    icon: str | None = None
    state_class: str | None = "measurement"
    _compiled_formula: CompiledFormula = PrivateAttr()

    @field_validator("setups", mode="before")
    @classmethod
    def validate_setups(cls, value: object) -> tuple[str, ...]:
        """Require custom readings to belong to at least one setup."""

        setups = normalize_setups(value)
        if setups is None:
            raise ValueError("custom measurements must declare setups")
        return setups

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, icon: str | None) -> str | None:
        """Normalize an optional Material Design entity icon."""

        return validate_measurement_icon(icon)

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, inputs: dict[str, str]) -> dict[str, str]:
        """Require at least one physical source with a safe local alias."""

        if not inputs:
            raise ValueError("custom measurements require at least one input")
        normalized: dict[str, str] = {}
        reserved = {"true", "false", "none", "null", "states", "is_number"}
        for alias, reference in inputs.items():
            clean_alias = alias.strip()
            if not clean_alias or slug(clean_alias) != clean_alias or keyword.iskeyword(clean_alias) or clean_alias in reserved:
                raise ValueError("input aliases must use non-reserved lowercase letters, numbers, and underscores")
            clean_reference = reference.strip()
            if clean_reference.count(".") != 1:
                raise ValueError(f"input {clean_alias} must reference service.measurement")
            normalized[clean_alias] = clean_reference
        if len(set(normalized.values())) != len(normalized):
            raise ValueError("custom measurement inputs must reference distinct measurements")
        return normalized

    @field_validator("constants", mode="before")
    @classmethod
    def validate_constants(cls, constants: object) -> dict[str, float]:
        """Require finite numeric constants with the same safe naming rules."""

        if not isinstance(constants, Mapping):
            raise ValueError("custom measurement constants must be a mapping")
        normalized: dict[str, float] = {}
        reserved = {"true", "false", "none", "null", "states", "is_number"}
        for name, raw_value in constants.items():
            if not isinstance(name, str):
                raise ValueError("custom measurement constant names must be strings")
            clean_name = name.strip()
            if not clean_name or slug(clean_name) != clean_name or keyword.iskeyword(clean_name) or clean_name in reserved:
                raise ValueError("constant names must use non-reserved lowercase letters, numbers, and underscores")
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)) or not math.isfinite(raw_value):
                raise ValueError("custom measurement constants must be finite numbers")
            normalized[clean_name] = float(raw_value)
        return normalized

    @model_validator(mode="after")
    def validate_formula(self) -> "CustomMeasurementConfig":
        """Ensure the formula uses every declared input and no unknown names."""

        overlap = sorted(set(self.inputs).intersection(self.constants))
        if overlap:
            raise ValueError("inputs and constants use the same names: " + ", ".join(overlap))
        compiled = compile_formula(self.formula, set(self.inputs) | set(self.constants))
        unused_inputs = sorted(set(self.inputs).difference(compiled.names))
        if unused_inputs:
            raise ValueError("formula does not use inputs: " + ", ".join(unused_inputs))
        unused_constants = sorted(set(self.constants).difference(compiled.names))
        if unused_constants:
            raise ValueError("formula does not use constants: " + ", ".join(unused_constants))
        self._compiled_formula = compiled
        return self

    @property
    def compiled_formula(self) -> CompiledFormula:
        """Return the arithmetic expression validated with this measurement."""

        return self._compiled_formula

    def display_label(self, custom_id: str) -> str:
        """Return the full label used outside compact dashboard rows."""

        return self.label or title(custom_id)

    def display_short_label(self, custom_id: str) -> str:
        """Return the compact dashboard label."""

        return self.short_label or self.display_label(custom_id)
