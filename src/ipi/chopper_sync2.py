import time
import numpy as np
import pyvisa
import struct

tdiv  = 0
delay = 0
fs    = 0

vdivs = [0, 0, 0, 0]
voffs = [0, 0, 0, 0]

import time
import numpy as np
from pyvisa import errors

def _drain_input(s, max_ms=2000):
    """Non-blocking drain of any leftover bytes in the input buffer."""
    old_to, old_rt = s.timeout, s.read_termination
    s.timeout, s.read_termination = 5, None
    t0 = time.time()
    try:
        while (time.time()-t0)*1000 < max_ms:
            try:
                junk = s.read_raw()
                print ("cleared byte")
                if not junk:
                    break
            except errors.VisaIOError as e:
                # timeout => buffer is empty
                if e.error_code == errors.VI_ERROR_TMO:
                    break
                raise
    finally:
        s.timeout, s.read_termination = old_to, old_rt

def _read_ieee_block_tolerant(s):
    """Read one IEEE-488.2 block, tolerating stray leading LF/CR and eating the optional trailing LF."""
    before = time.time_ns()
    old_rt = s.read_termination
    s.read_termination = None                      # raw bytes, no terminator handling
    after = time.time_ns()
    print (f"term chg{(after - before) / 1000000.0}")
    # Find '#'
    before = time.time_ns()
    #b = s.read_bytes(1)

    while True:
        b = s.read_bytes(1)
        print ('read garbag')
        if b == b'#':
            break
        if b in (b'\n', b'\r', b' '):
            continue  # skip whitespace/newlines
        # Any other stray byte: keep skipping until we see '#'

    after = time.time_ns()
    print (f"delete #{(after - before) / 1000000.0}")
    before = time.time_ns()

    nd = int(s.read_bytes(1).decode())
    n  = int(s.read_bytes(nd).decode())

    print (nd)
    after = time.time_ns()
    print (f"preamble #{(after - before) / 1000000.0}")

    before = time.time_ns()
    payload = s.read_bytes(n)
    after = time.time_ns()

    print (f"payload #{(after - before) / 1000000.0}")
    # Try to consume a single trailing LF without blocking
    old_to = s.timeout
    s.timeout = 1
    try:
        s.read_bytes(1)
    except errors.VisaIOError:
        print ('emptied')
        pass
    s.timeout = old_to
    s.read_termination = old_rt
    return payload

def fetch_c1_window(scope):
    """
    Atomic windowed fetch: clears buffer, sets STAR/POIN/SOUR, then reads the block safely.
    Returns uint8 numpy array.
    """
    # Known-good I/O state for this transaction
    #scope.write_termination = '\n'
    # 1) Drain leftovers from any prior failed read
    #_drain_input(scope)

    # 2) Batch the setters, then issue DATA?

    # 3) Read the block robustly
    block = _read_ieee_block_tolerant(scope)
    return np.frombuffer(block, dtype=np.uint8)
    
def read_channel(scope, source="C1"):
    global tdiv, delay, fs

    XINC  = 1.0 / fs
    XORIG = -delay - 5.0 * tdiv
    XREF  = 0.0

    before = time.time_ns()
    scope.write(":WAVeform:SOURce " + source)
    scope.write(":WAV:DATA?")
    after = time.time_ns()
    print (f"setmode #{(after - before) / 1000000.0}")
    print ("reading")
    u8 = fetch_c1_window(scope)
    print ("done read")
    print(f"{len(u8)}")

    s = u8.astype(np.int16); s[s > 127] -= 256

    # If YINC/yorig/yref weren’t available from PREamble, fall back per-channel
    # print(scope.query(f":CHANnel{source[1]}:SCALe?"))

    print(source)
    vdiv = vdivs[int(source[1])]
    voff = voffs[int(source[1])]
    volts = s * (vdiv / 25.0) - voff

    i = np.arange(volts.size, dtype=np.float64)
    t = (i - XREF) * XINC + XORIG
    return t, volts

def read_channels_once(scope, channels=("C1","C2","C3")):
    t = None
    traces = {}
    for ch in channels:
        t_ch, v = read_channel(scope, ch)
        time.sleep(0.1)
        if t is None:
            t = t_ch
        else:
            # ensure same length
            n = min(len(t), len(v))
            v = v[:n]; t = t[:n]
        traces[ch] = v
    return t, traces
 
#################################
# Edge detection & measurements #
#################################
 
def rising_edges_times(t, v, threshold, hysteresis=0.0):
    """
    Find rising edge times via linear interpolation:
    edge when v crosses from < (thr - hyst/2) to >= (thr + hyst/2).
    """
    low  = threshold - hysteresis/2
    high = threshold + hysteresis/2
    below = v[:-1] < low
    above = v[1:]  >= high
    idx = np.where(below & above)[0]
    # Linear interpolation: t_cross = t0 + (thr - v0) * (t1 - t0) / (v1 - v0)
    t0 = t[idx]
    t1 = t[idx+1]
    v0 = v[idx]
    v1 = v[idx+1]
    # Avoid division by 0 for flat steps
    dv = np.where((v1 - v0) == 0, 1e-12, v1 - v0)
    frac = (threshold - v0) / dv
    return t0 + frac * (t1 - t0)
 
def pairwise_delay_and_phase(tC2, tC3):
    """
    Compute:
      - latest rising-edge delay Δt = tC3_last - tC2_last
      - phase of latest laser edge relative to the most recent chopper revolution (0..360)
    Returns (delta_t, phase_deg, Tchop) or (None, None, None) if insufficient edges.
    """
    if len(tC2) < 2 or len(tC3) < 1:
        print("No values captured.")
        return None, None, None
 
    tC2_last = tC2[-1]
    tC3_last = tC3[-1]
    delta_t = tC3_last - tC2_last
 
    # Find the chopper interval that contains tC3_last
    # i.e., tC2[k] <= tC3_last < tC2[k+1]
    k = np.searchsorted(tC2, tC3_last) - 1
    if k < 0 or k+1 >= len(tC2):
        return delta_t, None, None
 
    Tchop = tC2[k+1] - tC2[k]
    if Tchop <= 0:
        return delta_t, None, None
 
    phase = 360.0 * (tC3_last - tC2[k]) / Tchop
    # Keep phase in [0, 360)
    phase = (phase % 360.0 + 360.0) % 360.0
    return delta_t, phase, Tchop
 
###########################
# Main acquisition loop   #
###########################
 
def configure_scope(scope):
    global tdiv, delay, fs
    """
    A reasonable setup for your signals:
      C1: LDR (ignored for now)
      C2: chopper sync 0..2V, 1ms pulse/rev
      C3: laser 0..5V, ~100 Hz, ~50% duty
    Adjust timebase/trigger to taste.
    """

    scope.write_termination = '\n'
    scope.read_termination = '\n'

    scope.chunk_size = 1024 * 1024

    scope.clear()
    scope.write("*CLS")
    print(scope.query("*IDN?"))
    # Make sure binary waveform transfers are 8-bit
    scope.write(":WAVeform:WIDTh BYTE")
    scope.write(":WAVeform:FORMat BYTE")
    scope.write(":ACQuire:TYPE NORMal")
    scope.write(f":ACQ:MDEP 10k")
 
    # Display channels on
    for ch in (1,2,3):
        scope.write(f":CHANnel{ch}:DISPlay ON")

        vdivs[ch] = float(scope.query(f":CHANnel{ch}:SCALe?"))
        voffs[ch] = float(scope.query(f":CHANnel{ch}:OFFSet?"))
 
    # Set thresholds (vertical scale up to you)
    # You can also let the scope keep whatever vertical settings you prefer.
    # scope.write(":CHAN1:SCALe 0.5")  # example
    # scope.write(":CHAN2:SCALe 1.0")
    # scope.write(":CHAN3:SCALe 2.0")
 
    # Timebase: show several laser periods; e.g., 2 ms/div -> 20 ms across screen (~2 periods @100 Hz)
    # Or pick something like 10 ms/div to see many edges.
    # scope.write(":TIMebase:SCALe 0.002")   # 10 ms/div (example)
    # scope.write(":TIMebase:POSition 0")   # trigger at center
 
    # Trigger on laser rising edge (Ch3)
    scope.write(":TRIGger:MODE NORMal")
    scope.write(":TRIGger:EDGE:SOURce C3")
    scope.write(":TRIGger:EDGE:SLOPe RISing")

    scope.write(":WAVeform:FORMat BYTE")
    scope.write(":WAVeform:WIDTh BYTE")
    scope.write(":WAVeform:STARt 0")
    scope.write(":WAVeform:POINt 1000")
    scope.write(":WAVeform:MODE NORM")
    scope.write(":WAVeform:INTerval 10")

    
    scope.write(":MEASure ON")
    scope.write(":MEASure:MODE ADVanced")
    scope.write(":MEASure:ADVanced:STYle M1")
    scope.write(":MEASure:ADVanced:LINenumber 2")
    scope.write(":MEASure:ADVanced:P1 ON")
    scope.write(":MEASure:ADVanced:P2 ON")

    scope.write(":MEASure:ADVanced:P1:TYPE PHA")
    scope.write(":MEASure:ADVanced:P2:TYPE SKEW")

    
    scope.write(":MEASure:ADVanced:P1:SOURce1 C3")  # laser vs chopper
    scope.write(":MEASure:ADVanced:P1:SOURce2 C2")

    scope.write(":MEASure:ADVanced:P2:SOURce1 C3")  # laser vs chopper
    scope.write(":MEASure:ADVanced:P2:SOURce2 C2")

    # scope.write(":TRIGger:EDGE:LEVel 2.5")  # around mid of 0..5V
 
    # Run continuously
    scope.write(":RUN")



    tdiv  = float(scope.query(":TIMebase:SCALe?"))
    delay = float(scope.query(":TIMebase:DELAy?"))
    fs    = float(scope.query(":ACQuire:SRATe?"))
 
def main(scope_addr="USB0::0xF4EC::0x100C::SDS2HBAX900425::INSTR",
         poll_hz=10.0,
         ch2_threshold=1.0,    # ~mid of 0..2V
         ch3_threshold=2.5,    # ~mid of 0..5V
         hysteresis=0.0):
    """
    Continuously poll the scope and print delay/phase.
    """
    rm = pyvisa.ResourceManager()
    scope = rm.open_resource(scope_addr)
    scope.timeout = 10000

    _drain_input(scope)
 
    configure_scope(scope)
 
    interval = 1.0 / max(1e-3, poll_hz)
    ema_phase = None
    ema_delay = None
    alpha = 0.3  # smoothing for readout

    while True:
        t, traces = read_channels_once(scope, channels=("C1",))
        print('donee')

 
    while True:
        t, traces = read_channels_once(scope, channels=("C1","C2","C3"))
        v2 = traces["C2"]
        v3 = traces["C3"]
 
        # Rising edges
        tC2 = rising_edges_times(t, v2, threshold=ch2_threshold, hysteresis=hysteresis)
        tC3 = rising_edges_times(t, v3, threshold=ch3_threshold, hysteresis=hysteresis)
 
        dt, phase, Tchop = pairwise_delay_and_phase(tC2, tC3)
 
        if dt is not None:
            ema_delay = dt if ema_delay is None else (1-alpha)*ema_delay + alpha*dt
        if phase is not None:
            ema_phase = phase if ema_phase is None else (1-alpha)*ema_phase + alpha*phase
 
        # Optional: compute laser frequency from consecutive C3 edges
        laser_freq = None
        if len(tC3) >= 2:
            Tlaser = np.diff(tC3).mean()
            if Tlaser > 0:
                laser_freq = 1.0 / Tlaser
 
        # Optional: chopper frequency
        chopper_freq = None
        if Tchop is not None and Tchop > 0:
            chopper_freq = 1.0 / Tchop
 
        # Print a compact status line
        msg = []
        if ema_delay is not None:
            msg.append(f"Δt(laser−chopper) = {ema_delay*1e3:.3f} ms")
        if ema_phase is not None:
            msg.append(f"phase = {ema_phase:6.2f}° (laser in chopper cycle)")
        if laser_freq is not None:
            msg.append(f"f_laser ≈ {laser_freq:6.2f} Hz")
        if chopper_freq is not None:
            msg.append(f"f_chop ≈ {chopper_freq:6.2f} Hz")
 
        if msg:
            print(" | ".join(msg))
 
        time.sleep(interval)

scope_usb = "USB0::0xF4EC::0x100C::SDS2HBAX900425::INSTR"
scope_ip = "TCPIP0::10.11.13.220::5025::SOCKET"
if __name__ == "__main__":
    # Put your VISA address here, or enumerate with pyvisa.ResourceManager().list_resources()
    main(scope_addr=scope_usb,
         poll_hz=10.0,
         ch2_threshold=1.0,
         ch3_threshold=2.5,
         hysteresis=0.1)
    