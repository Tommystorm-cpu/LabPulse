#ifndef LABPULSE_PIPE_SAMPLE_WRITER_H
#define LABPULSE_PIPE_SAMPLE_WRITER_H

#include <Arduino.h>

#include "Reading.h"

namespace LabPulse {

class PipeSampleWriter {
 public:
  explicit PipeSampleWriter(Print &output);

  void value(
      const __FlashStringHelper *name,
      const Reading &reading,
      uint8_t digits);
  void value(const char *name, const Reading &reading, uint8_t digits);
  void end();

 private:
  void prefix(const __FlashStringHelper *name);
  void prefix(const char *name);

  Print &output_;
  bool firstValue_;
};

}  // namespace LabPulse

#endif
