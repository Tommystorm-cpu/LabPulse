#include "PipeSampleWriter.h"

#include <math.h>

namespace LabPulse {

PipeSampleWriter::PipeSampleWriter(Print &output)
    : output_(output), firstValue_(true) {}

// The overloads accept names held in flash (F("name")) or ordinary character
// strings. Both write the same protocol; firstValue_ avoids a leading separator.
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
  // End this sample's line. Examples construct a fresh writer for each sample;
  // end() does not reset firstValue_ for reuse.
  output_.println();
}

}  // namespace LabPulse
