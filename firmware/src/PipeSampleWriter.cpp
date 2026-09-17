#include "PipeSampleWriter.h"

#include <math.h>

namespace LabPulse {

PipeSampleWriter::PipeSampleWriter(Print &output)
    : output_(output), firstValue_(true) {}

void PipeSampleWriter::prefix(const __FlashStringHelper *name) {
  if (!firstValue_) {
    output_.print(F(" | "));
  }
  firstValue_ = false;
  output_.print(name);
  output_.print(F(": "));
}

void PipeSampleWriter::prefix(const char *name) {
  if (!firstValue_) {
    output_.print(F(" | "));
  }
  firstValue_ = false;
  output_.print(name);
  output_.print(F(": "));
}

void PipeSampleWriter::value(
    const __FlashStringHelper *name,
    const Reading &reading,
    uint8_t digits) {
  prefix(name);
  if (reading.valid && isfinite(reading.value)) {
    output_.print(reading.value, digits);
  } else {
    output_.print(F("null"));
  }
}

void PipeSampleWriter::value(
    const char *name,
    const Reading &reading,
    uint8_t digits) {
  prefix(name);
  if (reading.valid && isfinite(reading.value)) {
    output_.print(reading.value, digits);
  } else {
    output_.print(F("null"));
  }
}

void PipeSampleWriter::end() {
  output_.println();
}

}  // namespace LabPulse
