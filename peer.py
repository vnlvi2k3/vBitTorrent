from utils import *
import argparse
from threading import Thread, Timer 
from operator import itemgetter
import datetime
import time 
from itertools import groupby
import mmap 
import warnings
warnings.filterwarnings("ignore")

from configs import CFG, Config
config = Config.from_json(CFG)
from HTTPCommunication import Message, Peer2Tracker, Peer2Peer, ChunkSharing
from request import HTTPRequest

next_call = time.time()

class Peer:
    def __init__(self, peer_id, rcv_port, send_port):
        self.peer_id = peer_id
        self.rcv_socket = set_socket(rcv_port)
        self.send_socket = set_socket(send_port)
        self.files = self.fetch_owned_files()
        self.is_in_send_mode = False
        self.downloaded_files = {}

    def send_segment(self, sock, data, addr):
        ip, dest_port = addr
        segment = HTTPRequest(src_port = sock.getsockname()[1],
                                dest_port = dest_port,
                                data = data)
        encryted_data = segment.data
        sock.sendto(encryted_data, addr)

    def split_file_to_chunks(self, file_path, rng):
        with open(file_path, 'r+b') as f:
            mm = mmap.mmap(f.fileno(), 0)[rng[0]: rng[1]]
            piece_size = config.constants.CHUNK_PIECES_SIZE
            return [mm[p: p+piece_size] for p in range(0, rng[1] - rng[0], piece_size)]
        
    def reassemble_file(self, chunks, file_path):
        with open(file_path, 'wb+') as f:
            for chunk in chunks:
                f.write(chunk)
            f.flush()
            f.close()

    def send_chunk(self, filename, rng, dest_peer_id, dest_port):
        file_path = f"{config.directory.peer_files_dir}peer_{self.peer_id}/{filename}"
        chunk_pieces = self.split_file_to_chunks(file_path, rng)

        temp_port = generate_random_port()
        temp_sock = set_socket(temp_port)
        for idx, chunk in enumerate(chunk_pieces):
            msg = ChunkSharing(src_peer_id = self.peer_id,
                                dest_peer_id = dest_peer_id,
                                filename = filename,
                                range = rng,
                                idx = idx,
                                chunk = chunk)
            log_content = f"The chunk {idx}/{len(chunk_pieces)} of file {filename} is being sent to peer {dest_peer_id}"
            log(peer_id = self.peer_id, content = log_content)
            self.send_segment(sock=temp_sock,
                              data=Message.encode(msg),
                              addr=('localhost', dest_port))
        #Tell tje neighbour peer that sending has finished (idx = -1)
        msg = ChunkSharing(src_peer_id = self.peer_id,
                            dest_peer_id = dest_peer_id,
                            filename = filename,
                            range = rng,
                            idx = -1)
        self.send_segment(sock=temp_sock,
                          data=Message.encode(msg),
                          addr=('localhost', dest_port))
        free_socket(temp_sock)
    
    def handle_requests(self, msg, addr):
        # If a peer ask about file's size
        if "size" in msg.keys() and msg["size"] == -1:
            self.tell_file_size(msg, addr)
        # If a peer ask for a chunk of file
        elif "range" in msg.keys() and msg["chunk"] is None:
            self.send_chunk(filename=msg["filename"],
                            rng=msg["range"],
                            dest_peer_id=msg["src_peer_id"],
                            dest_port=addr[1])
    
    def listen(self):
        while True:
            data, addr = self.send_socket.recvfrom(config.constants.BUFFER_SIZE)
            msg = Message.decode(data)
            self.handle_requests(msg, addr)

    def set_send_mode(self, filename):
        if filename not in self.files:
            log_content = f"You don't own the file {filename}"
            log(peer_id = self.peer_id, content = log_content)
            return
        mess = Peer2Tracker(peer_id=self.peer_id,
                            mode=config.tracker_requests_mode.OWN,
                            filename=filename)
        self.send_segment(sock=self.send_socket,
                          data=mess.encode(),
                          addr=tuple(config.constants.TRACKER_ADDR))
        
        if self.is_in_send_mode:
            log_content = f"You are already in SEND mode"
            log(peer_id = self.peer_id, content = log_content)
            return
        else:
            self.is_in_send_mode = True
            log_content = f"You are now in SEND mode"
            log(peer_id = self.peer_id, content = log_content)
            thread = Thread(target=self.listen)
            thread.setDaemon(True)
            thread.start()

    def ask_file_size(self, filename, fileowner):
        temp_port = generate_random_port()
        temp_sock = set_socket(temp_port)
        dest_peer = fileowner[0]

        mess = Peer2Peer(src_peer_id=self.peer_id,
                         dest_peer_id=dest_peer["peer_id"],
                         filename=filename)
        self.send_segment(sock=temp_sock,
                          data=mess.encode(),
                          addr=tuple(dest_peer["addr"]))
        while True:
            data, addr = temp_sock.recvfrom(config.constants.BUFFER_SIZE)
            dest_peer_response = Message.decode(data)
            size = dest_peer_response["size"]
            free_socket(temp_sock)
            return size
        
    def tell_file_size(self, msg, addr):
        filename = msg["filename"]
        file_path = f"{config.directory.peer_files_dir}peer_{self.peer_id}/{filename}"
        file_size = os.stat(file_path).st_size
        response_mess = Peer2Peer(src_peer_id=self.peer_id,
                                  dest_peer_id=msg["src_peer_id"],
                                  filename=filename,
                                  size=file_size)
        temp_port = generate_random_port()
        temp_sock = set_socket(temp_port)
        self.send_segment(sock=temp_sock,
                          data=response_mess.encode(),
                          addr=addr)
        free_socket(temp_sock)

    def receive_chunk(self, filename, rng, file_owner):
        dest_peer = file_owner[0]
        mess = ChunkSharing(src_peer_id=self.peer_id,
                            dest_peer_id=dest_peer["peer_id"],
                            filename=filename,
                            range=rng,
                            idx=-1) #To tell that we need chunk from dest_peer
        temp_port = generate_random_port()
        temp_sock = set_socket(temp_port)
        self.send_segment(sock=temp_sock,
                          data=mess.encode(),
                          addr=tuple(dest_peer["addr"]))
        log_content = f"I sent request for a chunk of file {filename} to peer {dest_peer['peer_id']}"
        log(peer_id = self.peer_id, content = log_content)
        
        while True:
            data, addr = temp_sock.recvfrom(config.constants.BUFFER_SIZE)
            mess = Message.decode(data)
            if mess["idx"] == -1: #EOF
                free_socket(temp_sock)
                return 
            self.downloaded_files[filename].append(mess)
        
    def sort_downloaded_chunks(self, filename):
        sort_result_by_range = sorted(self.downloaded_files[filename], key=itemgetter("range"))
        groupby_range = groupby(sort_result_by_range, key=itemgetter("range"))
        sorted_downloaded_chunks = []
        for key, group in groupby_range:
            sorted_group = sorted(list(group), key=itemgetter("idx"))
            sorted_downloaded_chunks.append(sorted_group)   
        return sorted_downloaded_chunks

    def split_file_owners(self, file_owners, filename):
        owners = []
        for owner in file_owners:
            if owner[0]["peer_id"] != self.peer_id:
                owners.append(owner)
        if len(owners) == 0:
            log_content = f"No other peer has the file {filename}"
            log(peer_id = self.peer_id, content = log_content)
            return
        #Sorted based on sending frequency
        owners = sorted(owners, key=lambda x: x[1], reverse=True)
        to_be_used_owners = owners[:config.constants.MAX_CONCURRENT_REQUESTS]

        log_content = f"You are going to download the file {filename} from {[owner[0]['peer_id'] for owner in to_be_used_owners]}"
        log(peer_id = self.peer_id, content = log_content)
        file_size = self.ask_file_size(filename, to_be_used_owners[0])
        log_content = f"The size of the file {filename} is {file_size} bytes"
        log(peer_id = self.peer_id, content = log_content)

        #After getting the size of the file, split the file into chunks among the owners
        n_chunk = file_size / len(to_be_used_owners)
        chunks_ranges = [(round(n_chunk*i), round(n_chunk*(i+1))) for i in range(len(to_be_used_owners))]

        #Create a thread for each owner to download respective chunk from it
        self.downloaded_files[filename] = []
        neighboring_peers_threads = []
        for idx, owner in enumerate(to_be_used_owners):
            thread = Thread(target=self.receive_chunk, args=(filename, chunks_ranges[idx], owner))  
            thread.setDaemon(True)
            thread.start()
            neighboring_peers_threads.append(thread)
        for thread in neighboring_peers_threads:
            thread.join()

        log_content = f"All chunks of file {filename} have been downloaded, but they must be REASSEMBLED"
        log(peer_id = self.peer_id, content = log_content)

        sorted_chunks = self.sort_downloaded_chunks(filename)
        log_content = f"All chunks of file {filename} have been SORTED, they are almost ready to be REASSEMBLED"
        log(peer_id = self.peer_id, content = log_content)

        #Assemble the chunks to rebuild the file
        total_file = []
        file_path = f"{config.directory.peer_files_dir}peer_{self.peer_id}/{filename}"
        for chunk in sorted_chunks:
            for piece in chunk:
                total_file.append(piece["chunk"])
        self.reassemble_file(chunks=total_file, file_path=file_path)
        #all done -> annouce the tracker that I own the file
        mess = Peer2Tracker(peer_id=self.peer_id,
                            mode=config.tracker_requests_mode.OWN,
                            filename=filename)
        self.send_segment(sock=self.send_socket,
                            data=mess.encode(),
                            addr=tuple(config.constants.TRACKER_ADDR))
        log_content = f"The file {filename} has been downloaded and saved"
        log(peer_id = self.peer_id, content = log_content)
        self.files.append(filename)

    def set_scrape_mode(self, filename):
        mess = Peer2Tracker(peer_id=self.peer_id,
                            mode=config.tracker_requests_mode.SCRAPE,
                            filename=filename)
        self.send_segment(sock=self.send_socket,
                          data=mess.encode(),
                          addr=tuple(config.constants.TRACKER_ADDR))
        log_content = f"You have asked the tracker to SCRAPE the file {filename}"
        log(peer_id = self.peer_id, content = log_content)

        while True:
            data, addr = self.send_socket.recvfrom(config.constants.BUFFER_SIZE)
            tracker_response = Message.decode(data)
            log_content = f'Scrape results for file {filename}: Number of seeders: {tracker_response["search_results"]["seeders"]}, Number of leechers: {tracker_response["search_results"]["leechers"]}'
            log(peer_id = self.peer_id, content = log_content)


    def set_download_mode(self, filename):
        file_path = f"{config.directory.peer_files_dir}peer_{self.peer_id}/{filename}"
        if os.path.isfile(file_path):
            log_content = f"You already have the file {filename}"
            log(peer_id = self.peer_id, content = log_content)
            return
        else:
            log_content = f"You are now DOWNLOADING the file {filename}"
            log(peer_id = self.peer_id, content = log_content)
            tracker_response = self.search_torrent(filename)
            file_owners = tracker_response["search_results"]
            self.split_file_owners(file_owners, filename)

    def search_torrent(self, filename):
        mess = Peer2Tracker(peer_id=self.peer_id,
                            mode=config.tracker_requests_mode.NEED,
                            filename=filename)
        temp_port = generate_random_port()
        search_sock = set_socket(temp_port)
        self.send_segment(sock=search_sock,
                          data=mess.encode(),
                          addr=tuple(config.constants.TRACKER_ADDR))
        while True:
            data, addr = search_sock.recvfrom(config.constants.BUFFER_SIZE)
            tracker_response = Message.decode(data)
            return tracker_response
        
    def fetch_owned_files(self):
        files = []
        peer_files_dir = f"{config.directory.peer_files_dir}peer_{self.peer_id}"
        if os.path.isdir(peer_files_dir):
            _, _, files = next(os.walk(peer_files_dir))
        else:
            os.makedirs(peer_files_dir)
        return files

    def exit_torrent(self):
        mess = Peer2Tracker(peer_id=self.peer_id,
                            mode=config.tracker_requests_mode.EXIT)
        self.send_segment(sock=self.send_socket,
                          data=Message.encode(mess),
                          addr=tuple(config.constants.TRACKER_ADDR))
        free_socket(self.send_socket)
        free_socket(self.rcv_socket)
        log_content = f"You have exited the torrent"
        log(peer_id = self.peer_id, content = log_content)

    def enter_torrent(self):
        mess = Peer2Tracker(peer_id=self.peer_id,
                            mode=config.tracker_requests_mode.REGISTER)
        self.send_segment(sock=self.send_socket,
                            data=Message.encode(mess),
                            addr=tuple(config.constants.TRACKER_ADDR))
        log_content = f"You have entered the torrent"
        log(peer_id = self.peer_id, content = log_content)

    def inform_tracker_periodically(self, interval):
        global next_call
        log_content = f"I am informing the tracker that I am still alive."
        log(peer_id = self.peer_id, content = log_content)

        mess = Peer2Tracker(peer_id=self.peer_id,
                            mode=config.tracker_requests_mode.REGISTER)
        self.send_segment(sock=self.send_socket,
                            data=mess.encode(),
                            addr=tuple(config.constants.TRACKER_ADDR))
        datetime.datetime.now()
        next_call = next_call + interval
        Timer(next_call - time.time(), self.inform_tracker_periodically, args=(interval,)).start()

def run(args):
    peer = Peer(peer_id=args.peer_id,
                rcv_port=generate_random_port(),
                send_port=generate_random_port())
    log_content = f"========================================\nPeer {args.peer_id} started just right now\n==================================================="
    log(peer_id = args.peer_id, content = log_content)
    print(f"Files owned by peer {args.peer_id}: {peer.files}")
    peer.enter_torrent()

    timer_thread = Thread(target=peer.inform_tracker_periodically, args=(config.constants.PEER_TIME_INTERVAL,))
    timer_thread.setDaemon(True)
    timer_thread.start()

    print(f"ENTER YOUR COMMANDS HERE:")
    while True:
        command = input()
        mode, filename = parse_command(command)

        if mode == 'send':
            peer.set_send_mode(filename)
        elif mode == 'download':
            thread = Thread(target=peer.set_download_mode, args=(filename,))
            thread.setDaemon(True)
            thread.start()
        elif mode == 'scrape':
            thread = Thread(target=peer.set_scrape_mode, args=(filename,))
            thread.setDaemon(True)
            thread.start()
        elif mode == 'exit':
            peer.exit_torrent()
            exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("peer_id", help="The ID of the peer you want to register", type=int)
    peer_args = parser.parse_args()

    run(args=peer_args)