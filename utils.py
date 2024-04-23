import socket
import random
import warnings
import os 
from datetime import datetime
from configs import CFG, Config
config = Config.from_json(CFG)

used_ports = set()

def set_socket(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('localhost', port))
    used_ports.add(port)

    return sock

def free_socket(sock):
    used_ports.remove(sock.getsockname()[1])
    sock.close()

def generate_random_port():
    available_ports = config.constants.AVAILABLE_PORTS_RANGE
    rand_port = random.randint(available_ports[0], available_ports[1])
    while rand_port in used_ports:
        rand_port = random.randint(available_ports[0], available_ports[1])

    return rand_port

def parse_command(command):
    parts = command.split(' ')
    try:
        if len(parts) == 4:
            mode = parts[2]
            filename = parts[3]
        elif len(parts) == 3:
            mode = parts[2]
            filename = ""
        return mode, filename
    except IndexError:
        warnings.warn("INVALID COMMAND FORMAT. TRY AGAIN.")
        return
    
def log(peer_id, content, is_tracker=False):

    if not os.path.exists(config.directory.logs_dir):
        os.makedirs(config.directory.logs_dir)

    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")

    content = f"[{current_time}] {content}\n"
    print(content)

    if is_tracker:
        logs_filename = config.directory.logs_dir + "tracker.log"
    else:
        logs_filename = config.directory.logs_dir + f"peer_{peer_id}.log"
    if not os.path.exists(logs_filename):
        with open(logs_filename, 'w') as f:
            f.write(content)
            f.close()
    else:
        with open(logs_filename, 'a') as f:
            f.write(content)
            f.close()
    

