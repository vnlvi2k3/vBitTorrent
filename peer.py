import pickle
from utils import *
import argparse
from threading import Thread, Timer, Event 
from operator import itemgetter
import datetime
import time 
from itertools import groupby
import mmap 
import warnings
from tqdm import tqdm
warnings.filterwarnings("ignore")

from configs import *
config = Config.from_json(CFG)
from HTTPCommunication import Message, Peer2Tracker, Peer2Peer, ChunkSharing
from request import HTTPRequest

next_call = time.time()
source_ip = get_loacal_ip()

class Peer:
    def __init__(self, peer_id, rcv_port, send_port):
        self.peer_id = peer_id
        self.rcv_socket = set_socket(rcv_port)
        self.send_socket = set_socket(send_port)
        self.files = self.fetch_owned_files()
        self.is_in_send_mode = False
        self.download_status = {}
        self.downloaded_files = {}
        self.send_sockets = {}
        self.receive_sockets = {}

    def send_segment(self, sock, data, addr):
        ip, dest_port = addr
        segment = HTTPRequest(src_ip=source_ip,
                                dest_ip = ip,
                                src_port = sock.getsockname()[1],
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

    def send_chunk(self, filename, rng, dest_peer_id, addr):
        if (self.peer_id, dest_peer_id, filename) not in self.send_sockets.keys():
            temp_port = generate_random_port()
            temp_sock = set_socket(temp_port)
            self.send_sockets[(self.peer_id, dest_peer_id, filename)] = temp_sock
        send_socket = self.send_sockets[(self.peer_id, dest_peer_id, filename)]

        if not self.download_status[filename]["bitfield"][rng[0] // config.constants.CHUNK_SIZE]:
            msg = ChunkSharing(src_peer_id = self.peer_id,
                            dest_peer_id = dest_peer_id,
                            filename = filename,
                            range = rng,
                            idx = -2) #Tell the neighbour peer that the chunk is not available
            self.send_segment(sock=send_socket,
                            data=Message.encode(msg),
                            addr=addr)
            return
            
        file_path = f"{config.directory.peer_files_dir}peer_{self.peer_id}/{filename}"
        chunk_pieces = self.split_file_to_chunks(file_path, rng)

        # log_content = f"Peer {self.peer_id} is sending {len(chunk_pieces)} chunks to peer {dest_peer_id}"
        # log(peer_id = self.peer_id, content = log_content)
        for idx, chunk in enumerate(chunk_pieces):
            msg = ChunkSharing(src_peer_id = self.peer_id,
                                dest_peer_id = dest_peer_id,
                                filename = filename,
                                range = rng,
                                idx = idx,
                                chunk = chunk)
            self.send_segment(sock=send_socket,
                            data=Message.encode(msg),
                            addr=addr)
        log_content = f"Peer {self.peer_id} has sent all chunks to peer {dest_peer_id}"
        log(peer_id = self.peer_id, content = log_content)  
        #Tell the neighbour peer that sending has finished (idx = -1)
        msg = ChunkSharing(src_peer_id = self.peer_id,
                            dest_peer_id = dest_peer_id,
                            filename = filename,
                            range = rng,
                            idx = -1)
        self.send_segment(sock=send_socket,
                          data=Message.encode(msg),
                          addr=addr)
    
    def handle_requests(self, msg, addr):
        # If a peer ask about file's size
        if "size" in msg.keys() and msg["size"] == -1:
            self.tell_file_size(msg, addr)
        # If a peer ask for a chunk of file
        elif "range" in msg.keys() and msg["chunk"] is None:
            self.send_chunk(filename=msg["filename"],
                            rng=msg["range"],
                            dest_peer_id=msg["src_peer_id"],
                            addr=addr)
    
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
        file_size = os.stat(f"{config.directory.peer_files_dir}peer_{self.peer_id}/{filename}").st_size
        print(f"File size: {file_size}")
        chunks_ranges = self.calculate_chunks_ranges(file_size)
        self.download_status[filename] = {
            "bitfield": [1] * len(chunks_ranges),
            "is_downloading": [0] * len(chunks_ranges),
            "chunks_ranges": chunks_ranges,
            "to_be_used_owners": None,
            "downloaded": True
        }
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
        print(f"File size: {file_size}")
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

    def receive_chunk(self, filename, file_owner, log_file_path):
        dest_peer = file_owner[0]
        temp_port = generate_random_port()
        receive_socket = set_socket(temp_port)
        # if (self.peer_id, dest_peer["peer_id"], filename) not in self.receive_sockets.keys():
        #     temp_port = generate_random_port()
        #     temp_sock = set_socket(temp_port)
        #     self.receive_sockets[(self.peer_id, dest_peer["peer_id"], filename)] = temp_sock
        # receive_socket = self.receive_sockets[(self.peer_id, dest_peer["peer_id"], filename)]

        for idx, rng in enumerate(self.download_status[filename]["chunks_ranges"]):
            if self.download_status[filename]["bitfield"][idx] == 0 and \
            self.download_status[filename]["is_downloading"][idx] == 0:
                self.download_status[filename]["is_downloading"][idx] = 1
                mess = ChunkSharing(src_peer_id=self.peer_id,
                                    dest_peer_id=dest_peer["peer_id"],
                                    filename=filename,
                                    range=rng,
                                    idx=-1)
                self.send_segment(sock=receive_socket,
                                data=mess.encode(),
                                addr=tuple(dest_peer["addr"]))
                received_chunks = []
                print(f"Peer {dest_peer['peer_id']} is sending chunk {idx}")

                # data, addr = receive_socket.recvfrom(config.constants.BUFFER_SIZE)
                # mess = Message.decode(data)
                # if mess["idx"] == -2 or self.download_status[filename]["is_downloading"][idx] == 1:
                #     print("Damn")
                #     continue
                # else:
                #     print(f"Peer {dest_peer['peer_id']} is sending chunk {idx}")
                #     self.download_status[filename]["is_downloading"][idx] = 1
                # received_chunks.append(mess)
                # self.downloaded_files[filename].append(mess)
                while True:
                    data, addr = receive_socket.recvfrom(config.constants.BUFFER_SIZE)
                    mess = Message.decode(data)
                    if mess["idx"] == -1: #EOF
                        break

                    self.downloaded_files[filename].append(mess)
                    received_chunks.append(mess)

                if not os.path.exists(log_file_path):
                    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
                with open(log_file_path, 'ab') as log_file:
                    pickle.dump((received_chunks, idx), log_file)
                self.download_status[filename]["bitfield"][idx] = 1
                self.download_status[filename]["progress"].update(1)
        print("Peer {dest_peer['peer_id']} has go through all bits")
        self.download_status[filename]["to_be_used_owners"].remove(file_owner)

        free_socket(receive_socket)
        

    def load_chunks_from_log(self, filename, log_file_path):
        if not os.path.isfile(log_file_path):
            return
        with open(log_file_path, 'rb') as log_file:
            while True:
                try:
                    loaded_data = pickle.load(log_file)
                    if isinstance(loaded_data, tuple) and len(loaded_data) == 2:
                        chunk, idx = loaded_data
                        self.downloaded_files[filename] += chunk
                        self.download_status[filename]["bitfield"][idx] = 1
                except EOFError:
                    break  # Đã đọc hết file log
                except pickle.UnpicklingError:
                    os.remove(log_file_path)
                    return
        
    def sort_downloaded_chunks(self, filename):
        sort_result_by_range = sorted(self.downloaded_files[filename], key=itemgetter("range"))
        groupby_range = groupby(sort_result_by_range, key=itemgetter("range"))
        sorted_downloaded_chunks = []
        for key, group in groupby_range:
            sorted_group = sorted(list(group), key=itemgetter("idx"))
            sorted_downloaded_chunks.append(sorted_group)   
        return sorted_downloaded_chunks
    
    def calculate_chunks_ranges(self, file_size):
        chunk_size = config.constants.CHUNK_SIZE
        num_chunks = (file_size + chunk_size - 1) // chunk_size
        
        # Tính toán các khoảng cho từng chunk
        chunks_ranges = []
        start = 0
        for _ in range(num_chunks):
            end = min(start + chunk_size, file_size)
            chunks_ranges.append((start, end))
            start = end

        return chunks_ranges

    def split_file_owners(self, file_owners, filename, isFirst=False):
        owners = []
        for owner in file_owners:
            if owner[0]["peer_id"] != self.peer_id:
                owners.append(owner)
        if len(owners) == 0:
            log_content = f"No other peer has the file {filename}"
            log(peer_id = self.peer_id, content = log_content)
            return
        #Sorted based on sending frequency
        # to_be_used_owners = sorted(owners, key=lambda x: x[1], reverse=True)
        to_be_used_owners = owners
        file_size = self.ask_file_size(filename, to_be_used_owners[0])

        if isFirst:
            log_content = f"You are going to download the file {filename} from {[owner[0]['peer_id'] for owner in to_be_used_owners]}"
            log(peer_id = self.peer_id, content = log_content)
            log_content = f"The size of the file {filename} is {file_size} bytes"
            log(peer_id = self.peer_id, content = log_content)

        chunks_ranges = self.calculate_chunks_ranges(file_size)
        log_file_path = f"{config.directory.peer_chunklog_dir}peer_{self.peer_id}/{filename}.log"
        #Create a thread for each owner to download respective chunk from it
        if isFirst:
            self.downloaded_files[filename] = []
            self.download_status[filename] = {  
                "bitfield": [0] * len(chunks_ranges),
                "is_downloading": [0] * len(chunks_ranges),
                "chunks_ranges": chunks_ranges,
                "to_be_used_owners": to_be_used_owners,
                "downloaded": False
            }
            self.load_chunks_from_log(filename, log_file_path)
        self.download_status[filename]["progress"] = tqdm(total = len(self.download_status[filename]["bitfield"]))
        self.download_status[filename]["progress"].update(sum(self.download_status[filename]["bitfield"]))
        neighboring_peers_threads = []
        # with tqdm(total = file_size) as pbar:

        for idx, owner in enumerate(to_be_used_owners):
            thread = Thread(target=self.receive_chunk, args=(filename, owner, log_file_path))  
            thread.setDaemon(True)
            thread.start()
            neighboring_peers_threads.append(thread)
        # for thread in neighboring_peers_threads:
        #     thread.join()
        if all(self.download_status[filename]["bitfield"]):
            self.download_status[filename]["downloaded"] = True

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
            if os.path.exists(log_file_path):
                os.remove(log_file_path)

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
            self.split_file_owners(file_owners, filename, isFirst=True)
            while not self.download_status[filename]["downloaded"]:
                bf = self.download_status[filename]["bitfield"]
                # print(f"still downloading {sum(bf) / len(bf) * 100}%")  
                tracker_response = self.search_torrent(filename)
                file_owners = tracker_response["search_results"]
                owners = [x for x in file_owners if x[0]["peer_id"] != self.peer_id]
                new_owners = [x for x in owners if x not in self.download_status[filename]["to_be_used_owners"]]
                removed_owners = [x for x in self.download_status[filename]["to_be_used_owners"] if x not in owners]
                if len(removed_owners) > 0:
                    print(f"Removed owners: {removed_owners}")
                    print(f"Current owners: {self.download_status[filename]['to_be_used_owners']}")
                    for x in removed_owners:
                        print(x)
                        self.download_status[filename]["to_be_used_owners"].remove(x)
                if len(new_owners) > 0:
                    # if len(self.download_status[filename]["to_be_used_owners"]) == 0:
                    self.download_status[filename]["is_downloading"] = [0] * len(self.download_status[filename]["is_downloading"])
                    self.download_status[filename]["to_be_used_owners"] += new_owners
                    self.split_file_owners(new_owners, filename)
                time.sleep(5)

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
        # log_content = f"I am informing the tracker that I am still alive."
        # log(peer_id = self.peer_id, content = log_content)

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