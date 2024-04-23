# Peer-to-Peer BitTorrent Simulation

## Overview
This project simulates a peer-to-peer BitTorrent network. To run this project, you need to open multiple terminals to simulate the interaction between peers and a tracker.

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
torrent -mode exit <FILE_NAME>
```
