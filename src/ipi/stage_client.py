import socket
import threading
import time
import queue
import math


STEPS_PER_ROT = 1600.0
LIN_LENGTH = 90.0 / (2.54 / STEPS_PER_ROT) # Length / (pitch / steps per revolution)

PI_ADDR = ("10.193.124.226", 11755)
PORT = 11756

STATE_IDLE = 0
STATE_HOMING = 1
STATE_MOVING = 2
STATE_OFFLINE = 3

#print(LIN_LENGTH)

EXPOSURE_OFFSET_Z = 101
EXPOSURE_OFFSET_X = -15

HOME_POS = 80.0
HOME_ANGLE = -2

def move_r_to_x_y(radius, x, y):
    if y == 0:
        return (0, radius)
    
    #print(y / radius)
    angle = math.asin(y / radius)
    displacement = math.cos(angle) * radius

    return (angle, x - displacement) # target rot angle, lin position

class StepperClient:
    def __init__(self, port, addr):
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__bind_port = port
        self.__server_address = addr
        self.__last_reply = 0
        self.__shutdown = False
        self.__online = False
        self.__last_ack_seq = -1
        self.__next_seq = 0
        self.__enabled = False

        self.__positions = dict()
        self.__moving = dict()
        self.__home = dict()

        self.__command_queue = queue.Queue()

        self.__receiver = threading.Thread(target=self.__receive_thread, daemon=True) 
        self.__receiver.start()

        self.__connection = threading.Thread(target=self.__connection_thread, daemon=True) 
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
            self.__send_data()
            time.sleep(0.01)

    def __send_data(self):
        try:
            if not self.__online or time.time() - self.__last_reply > 15:
                if self.__last_reply != 0:
                    print("Timed out!")
                
                self.__sock.sendto(b"REQ_CONN", self.__server_address)
                time.sleep(1)

            elif not self.__command_queue.empty():
                self.__sock.sendto(self.__command_queue.get(), self.__server_address)

        except OSError:
            print("Failed to send data!")
            raise


    def __receive_thread(self):
        print(f"Binding port {self.__bind_port} for incoming connections")
        self.__sock.bind(("0.0.0.0", self.__bind_port))

        while not self.__shutdown:
            self.__receive()

    def __receive(self):
        try:
            data, addr = self.__sock.recvfrom(1024)
            #print(f"Received {data} from {addr}")
            data_str = data.decode("utf-8")

            #print(data_str)
            self.__parse(data_str)
            self.__last_reply = time.time()
            self.__online = True
        except ConnectionResetError:
            if not self.__online:
                pass
            else:
                print("Server appears to be down, failed to connect.")
                self.__online = False
            time.sleep(0.1)

    def __parse(self, data : str):
        blocks = data.strip().split(';')

        for block in blocks:
            if len(block) == 0:
                continue

            tokens = block.split(',')
            b_type = tokens[0]

            #print(b_type)

            if b_type == 'S':
                self.__last_ack_seq = int(tokens[1])
                continue
            elif b_type == 'E':
                self.__enabled = tokens[1] == "True"
                continue

            stepper = int(tokens[1])

            if b_type == 'P':
                self.__positions[stepper] = int(tokens[2])
            elif b_type == 'M':
                self.__moving[stepper] = tokens[2] == "True"
            elif b_type == 'H':
                self.__home[stepper] = int(tokens[2]) if tokens[2] != "None" else None
            

    def __queue_command(self, command, args):
        args_str = ""
        for arg in args:
            args_str += str(arg) + ','

        args_str = args_str.removesuffix(',')
        
        to_send = (f"{self.__next_seq},{command},{args_str}").encode("utf-8")
        self.__command_queue.put(to_send)

        self.__next_seq += 1

    def queue_move(self, stepper, steps):
        self.__queue_command("MOVE", [stepper, int(steps)])

    def queue_set(self, stepper, steps):
        self.__queue_command("SET", [stepper, steps])

    def queue_home(self, stepper, home, speed):
        self.__queue_command("HOME", [stepper, ("T" if home else "F"), int(speed)])

    def get_position(self, stepper):
        return self.__positions[stepper]
    
    def get_home(self, stepper):
        return self.__home[stepper]
    
    def is_moving(self, stepper = None):
        if stepper is None:
            for s in self.__moving.values():
                if s:
                    return True
            return False
        
        return self.__moving[stepper]
    
    def wait_flush(self, timeout = 60):
        start_time = time.time()
        while not self.__command_queue.empty() and (time.time() - start_time) < timeout:
            time.sleep(0.01)

        if (time.time() - start_time) > timeout:
            raise TimeoutError("Timed out")
        
    def wait_ack(self, timeout = 60):
        self.wait_flush(timeout)

        start_time = time.time()
        while self.__last_ack_seq < (self.__next_seq - 1) and (time.time() - start_time) < timeout:
            time.sleep(0.01)

        if (time.time() - start_time) > timeout:
            raise TimeoutError("Timed out")
        
    def is_online(self):
        return self.__online and (time.time() - self.__last_reply < 15)
    
    def is_enabled(self):
        return self.__enabled

class StageController:
    def __init__(self, client : StepperClient):
        self.__client = client
        self.__opqueue = queue.Queue()
        self.__shutdown_flag = False

        self.__busy = False
        self.__state = STATE_IDLE

        threading.Thread(target=self.__worker, daemon=True).start()

        self.__build_sample_data()

    def __worker(self):
        while not self.__shutdown_flag:
            if not self.__client.is_online():
                self.__state = STATE_OFFLINE
                time.sleep(1)
                continue
            elif self.__state == STATE_OFFLINE:
                self.__state = STATE_IDLE
                

            if not self.__opqueue.empty():
                func, args = self.__opqueue.get()
                func(*args)
                self.__state = STATE_IDLE

            time.sleep(0.1)
            

    def __move_blocking(self, stepper, target, timeout = 1.0):
        target = int(target)
        self.__client.queue_move(stepper, target)
        self.__client.wait_flush()

        start_time = time.time()
        self.__client.wait_ack()
        while not self.__client.is_moving() and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        while self.__client.is_moving():
            time.sleep(0.1)

        start_time = time.time()
        while self.__client.get_position(stepper) != target and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        if (time.time() - start_time) > timeout:
            raise TimeoutError("Timeout while waiting for motion")
        
    def __homing_routine(self):
        self.__state = STATE_HOMING

        self.__home_lin()
        self.__home_rot()

        self.__state = STATE_HOMING

    def __rot_homing_routine(self):
        self.__state = STATE_HOMING

        self.__home_rot()

        self.__state = STATE_HOMING
        
    def __home_lin(self):
        self.__client.queue_move(0, 0)
        self.__client.wait_ack()
        time.sleep(0.5)
        while self.__client.is_moving():
            time.sleep(0.1)

        self.__client.queue_set(0, 0)
        self.__client.queue_set(1, 0)
        self.__client.wait_ack()

        self.__move_blocking(1, LIN_LENGTH * 1.2)
        self.__client.queue_set(1, 0)
        self.__client.queue_move(1, 0)
        self.__client.wait_ack()
       
    def __home_rot(self):
        self.__move_blocking(1, -HOME_POS / (2.54 / STEPS_PER_ROT))
        time.sleep(0.1)

        self.__move_blocking(0, STEPS_PER_ROT * -0.3)

        self.__client.queue_set(0, 0)
        self.__move_blocking(0, STEPS_PER_ROT * 1.2)
        self.__client.queue_set(0, 0)
        self.__client.queue_home(0, True, 400)
        self.__client.queue_move(0, STEPS_PER_ROT * 1.2)
        self.__client.wait_ack()

        time.sleep(0.5)
        while self.__client.is_moving():
            time.sleep(0.1)

        h_pos = self.__client.get_home(0)
        if h_pos is None:
            raise Exception("Could not home rot!")
        time.sleep(1)

        self.__move_blocking(0, STEPS_PER_ROT * 0.9)

        self.__client.queue_home(0, True, 50)
        self.__client.queue_move(0, STEPS_PER_ROT * 1.2)
        self.__client.wait_ack()

        time.sleep(0.5)
        while self.__client.is_moving():
            time.sleep(0.1)

        h_pos = self.__client.get_home(0)
        if h_pos is None:
            raise Exception("Could not home rot!")
        
        time.sleep(0.5)
        self.__client.queue_set(0, 0)
        self.__client.wait_ack()
        self.__move_blocking(0, STEPS_PER_ROT * (HOME_ANGLE / 360.0))
        self.__client.queue_set(0, 0)
        self.__client.queue_move(0, 0)
        self.__client.wait_ack()
        time.sleep(0.5)

    def __shortest_path(self, a2):
        a1 = (-self.__client.get_position(0) / STEPS_PER_ROT) * 2 * math.pi

        a1_clamped = a1 % (2.0 * math.pi)
        a1_clamped += 2.0 * math.pi if a1_clamped < 0 else 0

        nt = a2 + a1 - a1_clamped
        if a2 - a1_clamped > math.pi:
            nt -= 2.0 * math.pi
        if a2 - a1_clamped < -math.pi:
            nt += 2.0 * math.pi

        return nt
    
    def __move(self, th, z):
        self.__state = STATE_MOVING

        self.__client.queue_move(1, -z / (2.54 / STEPS_PER_ROT))
        th1 = self.__shortest_path(th)
        self.__move_blocking(0, (-th1 / (math.pi * 2)) * STEPS_PER_ROT)

        self.__state = STATE_IDLE

    def __build_sample_data(self):
        self.__samples = []
        inner_radius_mm = 0.835 * 25.4
        outer_radius_mm = 1.645 * 25.4
        
        #Inner targets (processed second)
        for quadrant in range(4):
            angle = 45 + 90 * quadrant
            self.__samples.append({
                'ring': 1,
                'position': quadrant,
                'angle': angle,
                'label': f"Inner-Q{quadrant+1}",
                'radius': inner_radius_mm,
            })
        
        #Outer targets (processed first)
        for quadrant in range(4):
            base_angle = 90 * quadrant
            for i, offset in enumerate([21.04, 68.96]):
                angle = base_angle + offset
                self.__samples.append({
                    'ring': 2,
                    'position': quadrant * 2 + i,
                    'angle': angle,
                    'label': f"Outer-Q{quadrant+1}-{i+1}",
                    'radius': outer_radius_mm,
                })
    def __rotate_sample_routine(self, sample_index, offset = [0, 0]):
        sample = self.__samples[sample_index]

        #print(f"SELECT radius: {sample['radius']}, angle: {sample['angle']}, ring: {sample['ring']}, position: {sample['position']}")
        th, z = 0, 0

        th, z = move_r_to_x_y(sample['radius'], EXPOSURE_OFFSET_Z + offset[0], EXPOSURE_OFFSET_X + offset[1]) ##Lin cannot reach target z, have to compromise

        th += (sample['angle'] / 360.0) * math.pi * 2

        z = min(z, 89.5)

        self.__move(th, z)

    def goto_sample(self, sample, offset = [0, 0]):
        #if self.__state != STATE_IDLE:
        #    return False
        
        q_item = (self.__rotate_sample_routine, (sample, offset))
        self.__opqueue.put(q_item)
        time.sleep(0.1)
        
    
    def home(self):
        #if self.__state != STATE_IDLE:
        #    return False
        
        q_item = (self.__homing_routine, ())
        self.__opqueue.put(q_item)
        time.sleep(0.1)

    def home_rot(self):
        #if self.__state != STATE_IDLE:
        #    return False
        
        q_item = (self.__rot_homing_routine, ())
        self.__opqueue.put(q_item)
        time.sleep(0.1)

    def move_to(self, th, z):
        #if self.__state != STATE_IDLE:
        #    return False
        
        q_item = (self.__move, (th, z))
        self.__opqueue.put(q_item)
        time.sleep(0.1)

    def get_position(self):
        th = (-self.__client.get_position(0) / STEPS_PER_ROT) * 2 * math.pi
        z = -self.__client.get_position(1) * (2.54 / STEPS_PER_ROT)

        return (th, z)
    
    def wait_idle(self):
        while self.__state != STATE_IDLE:
            time.sleep(0.1)

    def get_state(self):
        return self.__state
    
    def is_enabled(self):
        return self.__client.is_enabled()
    
    def is_at_limit(self):
        return (-self.__client.get_position(1) * (2.54 / STEPS_PER_ROT)) >= 89.45


if __name__ == "__main__":
    client = StepperClient(11756, ("10.193.124.226", 11755))
    ctl = StageController(client)
    time.sleep(1)
    #ctl.move_to(0, 85)
    #ctl.home()
    #time.sleep(10)
    #ctl.move_routine(0, EXPOSURE_OFFSET_X)
    #time.sleep(1)

    try:
        #while not client.is_shutdown():
        #    break
        for i in [11, 4, 10, 3, 0, 5, 9, 2, 1, 6, 8, 7]:
            ctl.goto_sample(i)
            ctl.wait_idle()

        #ctl.move_to(0, 85)
    except:
        raise
    finally:
        client.close()