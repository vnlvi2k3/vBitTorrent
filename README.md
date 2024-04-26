# Peer-to-Peer BitTorrent Simulation

## Overview

This project simulates a peer-to-peer BitTorrent network. To run this project, you need to open multiple terminals to simulate the interaction between peers and a tracker.
![image](https://github.com/vnlvi2k3/vBittorrent/assets/139733764/c84e2f5f-480a-42ac-b098-f2694947e07e)

# BitTorrent Overview

BitTorrent is a peer-to-peer (P2P) file sharing protocol used for distributing large amounts of data over the Internet. Unlike traditional client-server models, BitTorrent allows users to download and upload portions of a file simultaneously, leveraging the collective bandwidth of all peers involved.

### Key Features:
1. **Peer-to-Peer:** Utilizes a decentralized network of interconnected peers without relying on a central server for file distribution.
2. **Torrent Files:** Metadata files (.torrent) contain information about files to be shared and tracker servers that help coordinate file transfers.
3. **Swarm Sharing:** Peers collaborate in a swarm to exchange pieces of the file, improving download speeds and reliability.
4. **Piece-wise Transfer:** Files are divided into small pieces, allowing peers to download and upload concurrently, enhancing overall download efficiency.
5. **Seeders and Leechers:** Seeders are peers with complete copies of the file, while leechers are peers downloading parts of the file. Peers may transition between these roles during sharing.
6. **Resilience:** BitTorrent can handle network fluctuations and intermittent connectivity issues gracefully due to its distributed nature.

### Usage:
Users typically use BitTorrent clients (e.g., uTorrent, qBittorrent) to download and share files. They add torrent files or magnet links to their client, which connects them to the swarm for file exchange.

### Legal Considerations:
While BitTorrent itself is a legal technology, it's crucial to respect copyright laws and only share/download authorized content.

### Benefits:
BitTorrent is efficient for distributing large files, reduces server bandwidth costs, and offers robustness against network failures.


## Prerequisites

Ensure Python is installed on your system to execute the Python scripts involved in this simulation.

## Setup and Running Instructions

### Start the Tracker

Open the first terminal and start the tracker by running:

```bash
python tracker.py
```

### Start Peers

In additional terminals, start each peer by running:

```bash
python peer.py <PEER_ID>
```

Replace `<PEER_ID>` with a unique identifier you wish to use for registering a peer. Each peer will maintain its own database, located in the directory:

### File Management

Each peer will have its own database located at:

```bash
./peer_files/peer_<PEER_ID>
```

To upload or download files, they must exist within this directory.

### Peer Commands

Execute the following commands in the peer terminals to interact with the BitTorrent network:

- To upload a file:

```bash
torrent -mode send <FILE_NAME>
```

- To download a file:

```bash
torrent -mode download <FILE_NAME>
```

- To retrieve information (number of leechers, seeders) about a file:

```bash
torrent -mode scrape <FILE_NAME>
```

- To exit the peer session

```bash
torrent -mode exit
```

### Tracker Commands

Execute the following commands in the tracker terminals to interact with the BitTorrent network:

- To show all sended files:

```bash
torrent -mode list
```

- To show all sended file's info:

```bash
torrent -mode fileinfo <FILE_NAME>
```

- To show all active peer info:

```bash
torrent -mode peerinfo
```
