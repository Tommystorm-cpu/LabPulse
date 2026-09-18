#ifndef LABPULSE_READING_H
#define LABPULSE_READING_H

namespace LabPulse {

// A valid zero is a measurement. When valid is false, ignore value: the serial
// writer emits null so the Pi can let that channel expire instead of using zero.
struct Reading {
  float value;
  bool valid;
};

}  // namespace LabPulse

#endif
