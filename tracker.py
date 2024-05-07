from threading import Thread, Timer
from collections import defaultdict
import json
import datetime
import time
import warnings
warnings.filterwarnings("ignore")

from utils import * 
from request import HTTPRequest
from HTTPCommunication import Message, Tracker2Peer
from configs import CFG, Config
config = Config.from_json(CFG)

next_call = time.time()

class Tracker:
    def __init__(self):
        self.tracker_socket = set_socket(config.constants.TRACKER_ADDR[1])
        self.file_owners_list = defaultdict(list)
        self.send_freq_list = defaultdict(int) 
        self.has_informed_tracker = defaultdict(bool)

    def send_segment(self, sock, data, addr):
        ip, dest_port = addr
        segment = HTTPRequest(src_ip=config.constants.TRACKER_ADDR[0],
                                dest_ip = ip,
                                src_port = sock.getsockname()[1],
                                dest_port = dest_port,
                                data = data)
        encryted_data = segment.data 
        sock.sendto(encryted_data, addr)

    def add_file_owner(self, msg, addr, status = 'seeder'):
        entry = {
            'peer_id': msg["peer_id"],
            'addr': addr,
            'status': status,
        }
        if status == 'seeder':
            log_content = f'Peer {msg["peer_id"]} registered as owner of file {msg["filename"]}'
            log(peer_id = 0, content = log_content, is_tracker = True)

        #if entry already in list as a leeacher, and the status is seeder, update the status to seeder
        found = False
        current_owners = [json.loads(entry) for entry in self.file_owners_list[msg["filename"]]]
        for json_entry in current_owners:
            if json_entry["peer_id"] == msg["peer_id"]:
                if json_entry["status"] != status:
                    json_entry["status"] = status
                    found = True
                    break
                else:
                    return
        if not found:
            self.file_owners_list[msg['filename']].append(json.dumps(entry))
            self.file_owners_list[msg['filename']] = list(set(self.file_owners_list[msg['filename']]))
        else:
            self.file_owners_list[msg["filename"]] = [json.dumps(entry) for entry in current_owners]

        self.save_db_as_json()
    
    def update_db(self, msg):
        self.send_freq_list[msg["peer_id"]] += 1
        self.save_db_as_json()

    def search_file(self, msg, addr):
        log_content = f"Peer {msg['peer_id']} requested file {msg['filename']}"
        log(peer_id = 0, content = log_content, is_tracker = True)

        matched_entries = []
        for json_entry in self.file_owners_list[msg["filename"]]:
            entry = json.loads(json_entry)
            matched_entries.append((entry, self.send_freq_list[entry["peer_id"]]))
        
        tracker_response = Tracker2Peer(dest_peer_id = msg["peer_id"],
                                        search_results = matched_entries,
                                        filename = msg["filename"])
        #update the status of the peer to leecher if len(matched_entries) > 0
        if len(matched_entries) > 0:
            #if peer_id not in matched_entries, add it 
            if msg["peer_id"] not in [entry[0]["peer_id"] for entry in matched_entries]:
                log(peer_id = 0, content = log_content, is_tracker = True)
                self.add_file_owner(msg, addr, status = 'leecher')
        
        self.send_segment(sock = self.tracker_socket,
                        data = tracker_response.encode(),
                        addr = addr)
        
    def remove_peer(self, peer_id, addr):
        entry = {
            'peer_id': peer_id,
            'addr': addr,
            'status': 'seeder',
        }
        try:
            self.send_freq_list.pop(peer_id)
        except KeyError:
            pass
        self.has_informed_tracker.pop((peer_id, addr))
        peer_files = self.file_owners_list.copy()
        for pf in peer_files:
            if json.dumps(entry) in peer_files[pf]:
                self.file_owners_list[pf].remove(json.dumps(entry))
            if len(self.file_owners_list[pf]) == 0:
                self.file_owners_list.pop(pf)
        
        self.save_db_as_json()

    def check_peer_periodically(self, interval):
        global next_call
        alive_peers_ids = set()
        dead_peers_ids = set()
        try:
            for peer, has_informed in self.has_informed_tracker.items():
                peer_id, peer_addr = peer[0], peer[1]
                if has_informed:
                    self.has_informed_tracker[peer] = False
                    alive_peers_ids.add(peer_id)
                else:
                    dead_peers_ids.add(peer_id)
                    self.remove_peer(peer_id, peer_addr)
        except RuntimeError:
            pass

        if not (len(alive_peers_ids) == 0 and len(dead_peers_ids) == 0):
            log_content = f"Peer(s) {list(alive_peers_ids)} is in torrent and peer(s) {list(dead_peers_ids)} have left the torrent."
            log(peer_id = 0, content = log_content, is_tracker = True)

        datetime.now()
        next_call = next_call + interval
        Timer(next_call - time.time(), self.check_peer_periodically, args=(interval,)).start()

    def save_db_as_json(self):
        if not os.path.exists(config.directory.tracker_db_dir):
            os.makedirs(config.directory.tracker_db_dir)

        peers_info_path = config.directory.tracker_db_dir + "peers_info.json"
        files_info_path = config.directory.tracker_db_dir + "files_info.json"

        temp_dict = {}
        for key, value in self.send_freq_list.items():
            temp_dict[f"peer_{key}"] = value
        with open(peers_info_path, 'w') as peers_json:
            json.dump(temp_dict, peers_json, indent=4, sort_keys=True)

        with open(files_info_path, 'w') as files_json:
            json.dump(self.file_owners_list, files_json, indent=4, sort_keys=True)

    #Implement TRACKER SCRAPE
    def handle_scrape_request(self, msg, addr):
        seeders = 0
        leechers = 0
        for json_entry in self.file_owners_list[msg["filename"]]:
            entry = json.loads(json_entry)
            if entry["status"] == 'seeder':
                seeders += 1
            else:
                leechers += 1

        response = {
            'seeders': seeders,
            'leechers': leechers,
        }
        tracker_response = Tracker2Peer(dest_peer_id = msg["peer_id"],
                                        search_results = response,
                                        filename = msg["filename"])
        self.send_segment(sock = self.tracker_socket,
                        data = tracker_response.encode(),
                        addr = addr)

    def handle_peer_request(self, data, addr):
        msg = Message.decode(data)
        mode = msg["mode"]
        if mode == config.tracker_requests_mode.REGISTER:
            self.has_informed_tracker[(msg["peer_id"], addr)] = True
        elif mode == config.tracker_requests_mode.OWN:
            self.add_file_owner(msg, addr, 'seeder')
        elif mode == config.tracker_requests_mode.NEED:
            self.search_file(msg, addr)
        elif mode == config.tracker_requests_mode.UPDATE:
            self.update_db(msg)
        elif mode == config.tracker_requests_mode.EXIT:
            self.remove_peer(msg["peer_id"], addr)
            log_content = f"Peer {msg['peer_id']} exited the torrent intentionally."
            log(peer_id = 0, content = log_content, is_tracker = True)
        elif mode == config.tracker_requests_mode.SCRAPE:
            self.handle_scrape_request(msg, addr)

    def listen(self):
        timer_thread = Thread(target=self.check_peer_periodically, args=(config.constants.TRACKER_TIME_INTERVAL,))  
        timer_thread.setDaemon(True)
        timer_thread.start()

        while True:
            data, addr = self.tracker_socket.recvfrom(config.constants.BUFFER_SIZE)
            thread = Thread(target=self.handle_peer_request, args=(data, addr))
            thread.setDaemon(True)
            thread.start()              

    def run(self):
        log_content = f"========================================\nTracker started at {config.constants.TRACKER_ADDR}\n==================================================="
        log(peer_id = 0, content = log_content, is_tracker = True)
        thread = Thread(target=self.listen)
        thread.daemon = True
        thread.start()
        # thread.join() # Comment this out if listen is intended to run indefinitely

        print(f"ENTER YOUR COMMANDS HERE:")
        while True:
            command = input()
            mode, filename = parse_command(command)
            
            if mode == 'list':
                # Open the JSON file
                files_info_path = config.directory.tracker_db_dir + "files_info.json"
                with open(files_info_path, 'r') as file:
                    data = json.load(file)

                # Print the keys
                for key in data.keys():
                    print(key)

            elif mode == 'fileinfo':
                files_info_path = config.directory.tracker_db_dir + "files_info.json"
                with open(files_info_path, 'r') as file:
                    data = json.load(file)
                if filename in data:
                    for peer_info in data[filename]:
                        peer_info_dict = json.loads(peer_info)
                        print(f"peer_id: {peer_info_dict['peer_id']}, ip: {peer_info_dict['addr'][0]}, port: {peer_info_dict['addr'][1]}, status: {peer_info_dict['status']}")
                else:
                    print(f"No information found for file: {filename}")
            elif mode == 'peerinfo':
                # Read and parse files_info.json
                files_info_path = config.directory.tracker_db_dir + "files_info.json"
                with open(files_info_path, 'r') as f:
                    files_info = json.load(f)

                # Read and parse peers_info.json
                peer_info_path = config.directory.tracker_db_dir + "peers_info.json"
                with open(peer_info_path, 'r') as f:
                    peers_info = json.load(f)

                # Create a set to store the tuples
                data_set = set()

                # Iterate over the data from files_info.json
                for file, peers in files_info.items():
                    for peer in peers:
                        # Parse the peer data
                        peer_data = json.loads(peer)
                        # Create a tuple and add it to the set
                        data_set.add((peer_data['peer_id'], peer_data['addr'][0], peer_data['addr'][1], peers_info.get(f'peer_{peer_data["peer_id"]}', -1)))

                for data in data_set:
                    print(f"peer_id: {data[0]}, ip: {data[1]}, port: {data[2]}, score: {data[3]}")
                #print(data_set)

if __name__ == "__main__":
    tracker = Tracker()
    tracker.run()