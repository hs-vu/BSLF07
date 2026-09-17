"""
Misst, wie lange ein kompletter Multiplex-Zyklus (4 Ziffern) tatsächlich dauert.
Auf dem Pi ausführen (mit angeschlossenem oder auch ohne Display, debug=True
funktioniert für reines Timing nicht, da dann keine echten GPIO-Calls laufen -
also mit debug=False und echten Pins testen).
"""
import time
from display import SevenSegmentDisplay

segment_pins = [2,3,4,17,27,22,0,5]
digit_pins = [6,13,19,26]

display = SevenSegmentDisplay(segment_pins, digit_pins, digit_active_high=True)

N = 200
start = time.perf_counter()
for i in range(N):
    display._show_single_digit(i % 4, i % 10, False)
elapsed = time.perf_counter() - start

per_write_call = elapsed / N
full_cycle = per_write_call * 4  # 4 Ziffern = 1 kompletter Durchlauf

print(f"Ein einzelner _show_single_digit()-Aufruf: {per_write_call*1000:.3f} ms")
print(f"Ein kompletter 4-Ziffern-Zyklus (ohne sleep): {full_cycle*1000:.3f} ms")
print(f"Das entspricht einer Refresh-Rate von: {1/full_cycle:.1f} Hz")
print()
print("Faustregel: >60 Hz = für's Auge flackerfrei, <30 Hz = deutlich sichtbares Flackern")

display.close()