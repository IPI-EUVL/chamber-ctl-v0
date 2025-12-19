import socket
import pyvisa
import threading
import time

SERVER_INCOMING_PORT_NUM = 11780
class ScopeServer:
    def __init__(self):
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__get_scope()
        self.__setup_measure()

        self.__recipients = []
        self.__scope_running = False

        self.__shutdown = False

        self.__server = threading.Thread(target=self.__server_thread, daemon=True) 
        self.__server.start()

        self.__receiver = threading.Thread(target=self.__receive_thread, daemon=True) 
        self.__receiver.start()

    def close(self):
        print("Shutting down server...")
        self.__shutdown = True
        time.sleep(1)
        self.scope.close()
        self.__sock.close()

    def __get_scope(self):
        print("Attempting to connect to scope...")
        rm = pyvisa.ResourceManager()
        scope_usb = "USB0::0xF4EC::0x100C::SDS2HBAX900425::INSTR"
        scope_ip = "TCPIP0::10.11.13.220::5025::SOCKET"
        self.scope = rm.open_resource(scope_usb)
        self.scope.timeout = 1000
        self.scope.write_termination = '\n'
        self.scope.read_termination  = '\n'
        print("Conencted!")

    def __setup_measure(self):
        # one-time setup
        #scope.write(":CHAN1:DISP ON; :CHAN2:DISP ON; :CHAN3:DISP ON")
        #scope.write(":TRIG:MODE NORM; :TRIG:EDGE:SOUR C3; :TRIG:EDGE:SLOP RIS")

        self.scope.write(f":CHAN{1}:VIS ON")  # Enable selected channel
        self.scope.write(f":CHAN{2}:VIS ON")  # Enable selected channel
        self.scope.write(f":CHAN{3}:VIS ON")  # Enable selected channel

        self.scope.write(":ACQ:MODE RT")         # Real-time acquisition
        self.scope.write(":ACQ:SRAT 200E6")      # 200 MSa/s Sampling Rate
        self.scope.write(":ACQ:MDEP 10M")        # Match screen memory depth (10Mpts)  
        self.scope.write(":TIMebase:SCALe 5e-3")       # 5ms per division
        self.scope.write(":TIMebase:DELay 8e-3")       # 5ms per division

        # Trigger settings
        self.scope.write(":TRIG:MODE NORM")  
        self.scope.write(":TRIG:TYPE EDGE")  
        self.scope.write(":TRIGger:EDGE:SLOPe RIS")  
        self.scope.write(":TRIGger:EDGE:LEVel 3.00")  
        self.scope.write(":TRIGger:COUPling DC")  # DC coupling as shown on screen  
        self.scope.write(":TRIGger:EDGE:SOUR C3")  # DC coupling as shown on screen  
        self.scope.write(f":ACQ:MDEP 10k")

        self.scope.write(":MEASure ON")
        self.scope.write(":MEASure:MODE ADVanced")
        self.scope.write(":MEASure:ADVanced:STYle M2")
        self.scope.write(":MEASure:ADVanced:LINenumber 12")
        self.scope.write(":MEASure:ADVanced:P1 ON")
        self.scope.write(":MEASure:ADVanced:P2 ON")
        self.scope.write(":MEASure:ADVanced:P3 ON")

        self.scope.write(":MEASure:ADVanced:P1:TYPE PHA")
        self.scope.write(":MEASure:ADVanced:P2:TYPE SKEW")

        
        self.scope.write(":MEASure:ADVanced:P1:SOURce1 C3")  # laser vs chopper
        self.scope.write(":MEASure:ADVanced:P1:SOURce2 C2")

        self.scope.write(":MEASure:ADVanced:P2:SOURce1 C3")  # laser vs chopper
        self.scope.write(":MEASure:ADVanced:P2:SOURce2 C2")


    def __server_thread(self):
        print("Starting server thread!")

        last_cli_update = 0
        while not self.__shutdown:
            self.__read_and_send()

            if time.time() - last_cli_update > 1:
                self.__update_clients()

    def __read_start(self):
        self.scope.write(":RUN")
        self.__scope_running = True

    def __read_stop(self):
        self.scope.write(":STOP")
        self.__scope_running = False

    def __update_clients(self):
        for recp in self.__recipients:
            if time.time() - recp["ping"] > 10.0:
                print(f"DEAD recipient! {recp["addr"]}")
                self.__recipients.remove(recp)

            if recp["action"].count("header") > 0:
                recp["action"].remove("header")

                self.__sock.sendto(self.__get_header(), recp["addr"])

    def __read_and_send(self):
        if self.__scope_running and len(self.__recipients) == 0:
            self.__read_stop()
            time.sleep(0.1)
        elif not self.__scope_running and len(self.__recipients) > 0:
            self.__read_start()
            time.sleep(0.1)

        dt, ph, vpp, filt, avg_vpp, amplitude, rms  = float('nan'), float('nan'), float('nan'), float('nan'), float('nan'), float('nan'), float('nan')
        try:
            ph = float(self.scope.query(":MEASure:ADVanced:P1:VALue?"))
            dt = float(self.scope.query(":MEASure:ADVanced:P2:VALue?"))
            vpp = float(self.scope.query(":MEASure:ADVanced:P3:VALue?"))
            filt = float(self.scope.query(":MEASure:ADVanced:P4:VALue?"))
            avg_vpp = float(self.scope.query(":MEASure:ADVanced:P5:VALue?"))
            amplitude = float(self.scope.query(":MEASure:ADVanced:P6:VALue?"))
            rms = float(self.scope.query(":MEASure:ADVanced:P7:VALue?"))

            if ph > 360:
                ph -= 360

            if ph < 0:
                ph += 360
        except ValueError:
            pass

        data = f"{time.time()},{dt*1e3},{ph},{vpp},{filt},{avg_vpp},{amplitude},{rms}".encode("utf-8")

        for recp in self.__recipients:
            self.__sock.sendto(data, recp["addr"])

    def __get_header(self):
        return b"t,skew,phase,vpp,filt,avg,amp,rms"


    def __receive_thread(self):
        print(f"Binding port {SERVER_INCOMING_PORT_NUM} for incoming connections")
        self.__sock.bind(("0.0.0.0", SERVER_INCOMING_PORT_NUM))

        while not self.__shutdown:
            self.__receive()

    def __receive(self):
        try:
            data, addr = self.__sock.recvfrom(1024)
            #print(f"Received {data} from {addr}")

            data_str = data.decode("utf-8")
            if data_str == "REQ_CONN":
                print(f"Received connection request from {addr}")
                for r in self.__recipients:
                    if r["addr"] == addr:
                        print("Repeated request, ignoring...")
                        return
                
                recipient = dict()
                recipient["addr"] = addr
                recipient["ping"] = time.time()
                recipient["action"] = []

                self.__recipients.append(recipient)
            
            elif data_str == "REQ_HEAD":
                print(f"Received header request from {addr}")
                for r in self.__recipients:
                    if r["addr"] == addr:
                        r["action"].append("header")
            elif data_str == "UPD_PING":
                for r in self.__recipients:
                    if r["addr"] == addr:
                        r["ping"] = time.time() #holy nesting

        except ConnectionResetError:
            pass


if __name__ == "__main__":
    try:
        server = ScopeServer()

        while True:
            time.sleep(1)
    finally:
        server.close()