import socket
import pyvisa
import threading
import time

class ScopeClient:
    def __init__(self, port, addr, handler):
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__bind_port = 11781
        self.__server_address = addr
        self.__last_reply = 0
        self.__shutdown = False
        self.__online = True

        self.__handler_func = handler

        self.__receiver = threading.Thread(target=self.__receive_thread, daemon=False) 
        self.__receiver.start()

        self.__connection = threading.Thread(target=self.__connection_thread, daemon=False) 
        self.__connection.start()

    def is_shutdown(self):
        return self.__shutdown

    def close(self):
        print("Shutting down client...")
        self.__shutdown = True
        time.sleep(1)

        #self.__connection.join()
        #self.__receiver.join()

        self.__sock.close()

    def __connection_thread(self):
        print("Starting connection thread!")

        while not self.__shutdown:
            self.__connect()
            time.sleep(1)

    def __connect(self):
        if not self.__online or time.time() - self.__last_reply > 15:
            if self.__last_reply != 0:
                print("Timed out!")
            
            self.__sock.sendto(b"REQ_CONN", self.__server_address)
        else:
            self.__sock.sendto(b"UPD_PING", self.__server_address)


    def __receive_thread(self):
        print(f"Binding port {self.__bind_port} for incoming connections")
        self.__sock.bind(("0.0.0.0", self.__bind_port))

        while not self.__shutdown:
            self.__receive()

    def __receive(self):
        try:
            data, addr = self.__sock.recvfrom(1024)
            #print(f"Received {data} from {addr}")
            self.__handler_func(data)

            data_str = data.decode("utf-8")
            self.__last_reply = time.time()
            self.__online = True
        except ConnectionResetError:
            if not self.__online:
                pass
            else:
                print("Server appears to be down, failed to connect.")
                self.__online = False
            time.sleep(0.1)

if __name__ == "__main__":
    server = ScopeClient(11781, ("127.0.0.1", 11780), print)

    try:
        while not server.is_shutdown():
            time.sleep(1)
    finally:
        server.close()