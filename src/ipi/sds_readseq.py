import pyvisa
import pylab as pl
import time as t
import math
import struct
import gc
"""Modify the following global variables according to the model"""
ADC_BIT = 12
TDIV_ENUM = [100e-12, 200e-12, 500e-12, \
 1e-9, 2e-9, 5e-9, 10e-9, 20e-9, 50e-9, 100e-9, 200e-9, 500e-9, \
 1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6, 100e-6, 200e-6, 500e-6, \
 1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3, 100e-3, 200e-3, 500e-3, \
 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]

def main_wf_desc(recv):
    data_width = recv[0x20:0x21+1]#01-16bit,00-8bit
    data_order = recv[0x22:0x23+1]#01-MSB,00-LSB
    WAVE_ARRAY_1 = recv[0x3c:0x3f+1]
    wave_array_count = recv[0x74:0x77+1]
    first_point = recv[0x84:0x87+1]
    sp = recv[0x88:0x8b+1]
    one_fram_pts = recv[0x74:0x77+1]#pts of single frame,maybe bigger than 12.5M
    read_frame = recv[0x90:0x93+1]#all sequence frames number return by this command
    sum_frame = recv[0x94:0x97+1]#all sequence frames number acquired
    v_scale = recv[0x9c:0x9f+1]
    v_offset = recv[0xa0:0xa3+1]
    code_per_div = recv[0xa4:0Xa7 + 1]
    adc_bit = recv[0xac:0Xad + 1]
    sn = recv[0xae:0xaf+1]
    interval = recv[0xb0:0xb3+1]
    delay = recv[0xb4:0xbb+1]
    tdiv = recv[0x144:0x145+1]
    probe = recv[0x148:0x14b+1]
    width = struct.unpack('h',data_width)[0]
    order = struct.unpack('h',data_order)[0]
    data_bytes = struct.unpack('i',WAVE_ARRAY_1)[0]
    point_num = struct.unpack('i',wave_array_count)[0]
    fp = struct.unpack('i',first_point)[0]
    sp = struct.unpack('i',sp)[0]
    sn = struct.unpack('h',sn)[0]
    one_fram_pts = struct.unpack('i',one_fram_pts)[0]
    read_frame = struct.unpack('i',read_frame)[0]
    sum_frame = struct.unpack('i',sum_frame)[0]
    interval = struct.unpack('f',interval)[0]
    delay = struct.unpack('d',delay)[0]
    tdiv_index = struct.unpack('h',tdiv)[0]
    probe = struct.unpack('f',probe)[0]
    vdiv = struct.unpack('f',v_scale)[0]*probe
    offset = struct.unpack('f',v_offset)[0]*probe
    code = struct.unpack('f', code_per_div)[0]
    if ADC_BIT>8:
        code = code/16
    adc_bit = struct.unpack('h', adc_bit)[0]
    tdiv = TDIV_ENUM[tdiv_index]
    print("data_bytes=",data_bytes)
    print("point_num=",point_num)
    print("fp=",fp)
    print("sp=",sp)
    print("sn=",sn)
    print("vdiv=",vdiv)
    print("offset=",offset)
    print("interval=",interval)
    print("delay=",delay)
    print("tdiv=",tdiv)
    print("probe=",probe)
    print("data_width=",width)
    print("data_order=",order)
    print("code=", code)
    print("adc_bit=", adc_bit)
    print("one_fram_pts=", one_fram_pts)
    print("read_frame=", read_frame)
    print("sum_frame=", sum_frame)
    return vdiv,offset,interval,delay,tdiv,code,one_fram_pts,read_frame,sum_frame
def main_time_stamp_deal(time):
    seconds = time[0x00:0x08] # type:long double
    minutes = time[0x08:0x09] # type:char
    hours = time[0x09:0x0a] # type:char
    days = time[0x0a:0x0b] # type:char
    months = time[0x0b:0x0c] # type:char
    year = time[0x0c:0x0e] # type:short
    seconds = struct.unpack('d',seconds)[0]
    minutes = struct.unpack('c', minutes)[0]
    hours = struct.unpack('c', hours)[0]
    days = struct.unpack('c', days)[0]
    months = struct.unpack('c', months)[0]
    year = struct.unpack('h', year)[0]
    months = int.from_bytes(months, byteorder='big', signed=False)
    days = int.from_bytes(days, byteorder='big', signed=False)
    hours = int.from_bytes(hours, byteorder='big', signed=False)
    minutes = int.from_bytes(minutes, byteorder='big', signed=False)
    print("{}/{}/{},{}:{}:{}".format(year,months,days,hours,minutes,seconds))
'''
Read data of all sequence frame.
PS.when total points num (single_frame_pts * frame_num) is bigger than 12.5Mpts, you have to
read more than one time.
Frames number and points number readed this time will saved in the head parameter, see
main_wf_desc.
'''
def main_all_frame(sds):
    sds.write(":WAVeform:SOURce C1")
    sds.write(":WAVeform:STARt 0")
    sds.write(":WAVeform:POINt 0")
    sds.write(":WAVeform:SEQUence 0,0")
    sds.timeout = 2000 #default value is 2000(2s)
    sds.chunk_size = 20*1024*1024 #default value is 20*1024(20k bytes)
    sds.write(":WAVeform:PREamble?")
    recv_all = bytes()

    #while True:
    #    try:
    #        sds.timeout = 100
    recv_all += sds.read_raw()
    #    except pyvisa.VisaIOError:
    #        break
    sds.timeout = 10000

    recv = recv_all[recv_all.find(b'#')+11:]
    print(len(recv))
    vdiv, ofst, interval, delay, tdiv, code, one_frame_pts, read_frame, sum_frame = main_wf_desc(recv)
    read_times = math.ceil(sum_frame/read_frame)
    print("read_times=",read_times)
    one_piece_num = float(sds.query(":WAVeform:MAXPoint?").strip())
    for i in range(0,read_times):
        sds.write(":WAVeform:SEQUence {},{}".format(0,read_frame*i+1))
        if i+1 == read_times:#frame num of last read time
            read_frame = sum_frame -(read_times-1)*read_frame
        sds.write(":WAVeform:PREamble?")
        recv_rtn = sds.read_raw()
        recv_desc = recv_rtn[recv_rtn.find(b'#')+11:]
        time_stamp = recv_desc[346:]
        if ADC_BIT > 8:
            sds.write(":WAVeform:WIDTh WORD")
        sds.write(":WAVeform:DATA?")
        recv_rtn = sds.read_raw().rstrip()
        block_start = recv_rtn.find(b'#')
        data_digit = int(recv_rtn[block_start + 1:block_start + 2])
        data_start = block_start + 2 + data_digit
        recv = list(recv_rtn[data_start:])
        for j in range(0,read_frame):
            time = time_stamp[16*j:16*(j+1)]#timestamp spends 16 bytes
            main_time_stamp_deal(time)
            if ADC_BIT > 8:
                start = int(j * one_frame_pts*2)
                end = int((j + 1) * one_frame_pts*2)
                data_recv = recv[start:end]
                convert_data = []
                for k in range(0, int(len(data_recv) / 2)):
                    data_16bit = data_recv[2 * k + 1] * 256 + data_recv[2 * k]
                    data = data_16bit >> (16 - ADC_BIT)
                    convert_data.append(data)
            else:
                start = int(j*one_frame_pts)
                end = int((j+1)*one_frame_pts)
                convert_data = recv[start:end]
            volt_value = []
            for data in convert_data:
                if data > pow(2, ADC_BIT - 1) - 1: # 12bit-2047,8bit-127
                    data = data - pow(2, ADC_BIT)
                else:
                    pass
                volt_value.append(data)
            print(volt_value[0: 10])
            print(volt_value[one_frame_pts: one_frame_pts + 10])
            print(volt_value[2 * one_frame_pts: 2 *one_frame_pts + 10])
            print(len(volt_value))
            time_value = []
            for idx in range(0,len(volt_value)):
                volt_value[idx] = volt_value[idx]/code*float(vdiv)-float(ofst)
                time_data = -(float(tdiv)*HORI_NUM/2)+idx*interval-delay#calc ch timestamp
                time_value.append(time_data)
            print('Data convert finish,start to draw!')
            pl.figure(figsize=(7,5))
            pl.plot(time_value,volt_value,markersize=2,label=u"Y-T")
            pl.legend()
            pl.grid()
            pl.show()
            pl.close()
            del volt_value,time_value,convert_data
            gc.collect()
    del recv
    gc.collect()
'''
Read data of single frame.
'''
def main_specify_frame(sds,frame_num):
    sds.write(":WAVeform:SOURce C2")
    sds.write(":WAVeform:STARt 0")
    sds.write(":WAVeform:POINt 0")
    sds.write(":WAVeform:SEQUence {},{}".format(frame_num,0))
    sds.timeout = 2000 # default value is 2000(2s)
    sds.chunk_size = 20 * 1024 * 1024 # default value is 20*1024(20k bytes)
    sds.write(":WAVeform:PREamble?")
    recv_all = sds.read_raw()
    recv = recv_all[recv_all.find(b'#')+11:]
    time_stamp = recv[346:]
    main_time_stamp_deal(time_stamp)
    vdiv, ofst, interval, delay, tdiv, code,one_frame_pts, read_frame, sum_frame = main_wf_desc(recv)
    print(sds.query(":WAVeform:MAXPoint?"))
    one_piece_num = float(sds.query(":WAVeform:MAXPoint?").strip())
    if one_frame_pts > one_piece_num:
        sds.write(":WAVeform:POINt {}".format(one_piece_num))
    if ADC_BIT > 8:
        sds.write(":WAVeform:WIDTh WORD")
    read_times = math.ceil(one_frame_pts / one_piece_num)
    data_recv = []
    for i in range(0, read_times):
        start = i * one_piece_num
        sds.write(":WAVeform:STARt {}".format(start))
        sds.write("WAV:DATA?")
        recv_rtn = sds.read_raw().rstrip()
        block_start = recv_rtn.find(b'#')
        data_digit = int(recv_rtn[block_start + 1:block_start + 2])
        data_start = block_start + 2 + data_digit
        recv_piece = list(recv_rtn[data_start:])
        data_recv += recv_piece
    print("len(data_recv)=", len(data_recv))
    convert_data = []
    if ADC_BIT > 8:
        for i in range(0, int(len(data_recv) / 2)):
            data_16bit = data_recv[2 * i + 1] * 256 + data_recv[2 * i]
            data = data_16bit >> (16 - ADC_BIT)
            convert_data.append(data)
    else:
        convert_data = data_recv
    volt_value = []
    for data in convert_data:
        if data > pow(2, ADC_BIT-1) - 1: # 12bit-2047,8bit-127
            data = data - pow(2, ADC_BIT)
        else:
            pass
        volt_value.append(data)
    time_value = []
    for idx in range(0, len(volt_value)):
        volt_value[idx] = volt_value[idx] / code * float(vdiv) - float(ofst)
        time_data = -(float(tdiv) * HORI_NUM / 2) + idx * interval - delay # calc ch timestamp
        time_value.append(time_data)
    print('Data convert finish,start to draw!')
    pl.figure(figsize=(7, 5))
    pl.plot(time_value, volt_value, markersize=2, label=u"Y-T")
    pl.legend()
    pl.grid()
    pl.show()
    pl.close()
    del volt_value, time_value, data_recv
    gc.collect()
if __name__=='__main__':
    HORI_NUM = 10
    _rm = pyvisa.ResourceManager()
    sds = _rm.open_resource("TCPIP0::10.11.13.220::5025::SOCKET")
    sds.write_termination = '\n'
    sds.read_termination = '\n'
    main_all_frame(sds)
    
    main_specify_frame(sds, 0)
    try:
        sds.read_raw()
    except:
        pass
    t.sleep(1)
    main_specify_frame(sds, 1)
    try:
        sds.read_raw()
    except:
        pass
    t.sleep(1)
    main_specify_frame(sds, 3)
    try:
        sds.read_raw()
    except:
        pass
    t.sleep(1)
    main_specify_frame(sds, 4)

    sds.close()