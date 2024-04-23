from peer import Peer
import hashlib
from utils import *
from threading import Thread
from configs import CFG, Config
config = Config.from_json(CFG)


class DHTPeer(Peer):
    def __init__(self, peer_id, rcv_port, send_port, dht_network):
        super().__init__(peer_id, rcv_port, send_port)
        self.dht_network = dht_network
        self.node_id = self.generate_node_id()

    def generate_node_id(self):
        return hashlib.sha256(self.peer_id.encode()).hexdigest()
    
    def generate_file_key(self, filename):
        return hashlib.sha256(filename.encode()).hexdigest()
    
    def set_send_mode(self, filename):
        if filename not in self.files:
            log_content = f"You don't own the file {filename}"
            log(peer_id = self.peer_id, content = log_content)
            return
        file_key = self.generate_file_key(filename)
        self.dht_network.store(file_key, (self.peer_id, self.node_id, self.get_peer_address()))
        
        if self.is_in_send_mode:
            log_content = f"You are already in SEND mode"
            log(peer_id=self.peer_id, content=log_content)
            return
        else:
            self.is_in_send_mode = True
            log_content = f"You are now in SEND mode"
            log(peer_id = self.peer_id, content = log_content)
            thread = Thread(target=self.listen)
            thread.setDaemon(True)
            thread.start()
        
    def get_peer_addr(self):
        return self.rcv_socket.getsockname()
    
    def search_torrent(self, filename):
        file_key = self.generate_file_key(filename)
        peers_holding_file = self.dht_network.find(file_key)
        return peers_holding_file
    
    def set_download_mode(self, filename):
        file_path = f"{config.directory.peer_files_dir}peer_{self.peer_id}/{filename}"
        if os.path.isfile(file_path):
            log_content = f"You already have the file {filename}"
            log(peer_id = self.peer_id, content = log_content)
            return
        else:
            log_content = f"You are now DOWNLOADING the file {filename}"
            log(peer_id = self.peer_id, content = log_content)
            file_owners = self.search_torrent(filename)
            self.split_file_owners(file_owners, filename)

    def enter_torrent(self):
        self.dht_network.nodes[self.node_id] = {'peer_id': self.peer_id, 'addr': self.get_peer_addr()}
        log_content = f"You have entered the torrent"
        log(peer_id = self.peer_id, content = log_content)

    def leave_torrent(self):
        self.dht_network.nodes.pop(self.node_id)
        log_content = f"You have left the torrent"
        log(peer_id = self.peer_id, content = log_content)

class DHTNetwork:
    def __init__(self):
        # node_info might contain details like (ip_address, port)
        self.nodes = {}
    
    def hash_key(self, key):
        return int(hashlib.sha256(key.encode()).hexdigest(), 16)
        
    def find(self, key):
        closest_nodes = self.get_closest_nodes(key)
        return closest_nodes

    def get_closest_nodes(self, key):
        sorted_nodes = sorted(self.nodes.items(), key=lambda node: self.distance(node[0], key))
        return [node[1] for node in sorted_nodes[:5]]  # return top 3 closest nodes

    def distance(self, node_id, key):
        return int(node_id, 16) ^ int(key, 16)
    
    def store(self, key, value):
        # Determine which nodes should store this key
        responsible_nodes = self.find_responsible_nodes(key)
        # Store the key-value pair in each of those nodes
        for node_id in responsible_nodes:
            if node_id in self.nodes:
                self.nodes[node_id]['data'][key] = value
            else:
                self.nodes[node_id] = {'data': {key: value}}

    def find_responsible_nodes(self, hashed_key, num_nodes=3):
        sorted_nodes = sorted(self.nodes, key=lambda node_id: self.xor_distance(node_id, hashed_key))
        # Return the IDs of the closest num_nodes nodes
        return sorted_nodes[:num_nodes]

    def xor_distance(self, node_id, hashed_key):
        node_hash = int(node_id, 16)
        return node_hash ^ hashed_key


    
