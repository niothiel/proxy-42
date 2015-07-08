import logging
import select
import socket
import struct
import sys
import threading
from base64 import b64encode
from ctypes import *
from fcntl import ioctl

from pfresolver import PFResolver

class HTTPSProxy:
    def __init__(self, proxy_url, proxy_port, proxy_username, proxy_password, listen_host=None, listen_port=3129, buffer_size=4096):
        self.proxy_url = proxy_url
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.listen_host = listen_host or ''
        self.listen_port = listen_port
        self.buffer_size = buffer_size
        self.credentials = b64encode('{}:{}'.format(self.proxy_username, self.proxy_password))
        self.running = False
        self.worker_thread = threading.Thread(target=self._worker_thread)
        self.worker_thread.daemon = True

        self.addr_resolver = PFResolver()

    def _start_proxy_listener(self, max_waiting_connections=20):
        proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        proxy_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        proxy_socket.bind((self.listen_host, self.listen_port))
        proxy_socket.listen(max_waiting_connections)

        sa = proxy_socket.getsockname()
        logging.info('Serving HTTPS proxy on %s:%s...', sa[0], sa[1])
        return proxy_socket

    def _proxy_connection_handler(self, client_socket):
        dest_ip, dest_port = self.addr_resolver.original_addr(client_socket)
        dest = '{}:{}'.format(dest_ip, dest_port)

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect((self.proxy_url, self.proxy_port))

        send_str = ('CONNECT {} HTTP/1.1\r\n' + \
            'Host: {}\r\n' + \
            'Proxy-Authorization: Basic {}\r\n' + \
            'Proxy-Connection: close\r\n\r\n').format(dest, dest, self.credentials)

        server_socket.send(send_str)
        response = server_socket.recv(self.buffer_size)
        if 'HTTP/1.1 200 Connection established' not in response:
            server_socket.close()
            client_socket.close()
            return

        logging.info('Destination: %s', dest)
        while self.running:
            socket_list = [server_socket, client_socket]
            readable_sockets, _, _ = select.select(socket_list, [], [], 2)
            for read_sock in readable_sockets:
                if read_sock is server_socket:
                    write_sock = client_socket
                elif read_sock is client_socket:
                    write_sock = server_socket
                else:
                    raise Error('Unknown read socket')

                try:
                    buf = read_sock.recv(self.buffer_size)
                    if not buf:
                        server_socket.close()
                        client_socket.close()
                        return
                    write_sock.send(buf)
                except Exception as e:
                    print 'Caught exception:', e
                    return

        client_socket.close()
        server_socket.close()

    def _worker_thread(self):
        proxy_socket = self._start_proxy_listener()

        while self.running:
            client_socket, _ = proxy_socket.accept()
            handlerThread = threading.Thread(target=self._proxy_connection_handler, args=(client_socket,))
            handlerThread.start()
            logging.info('Live Threads: %d', threading.active_count())

    def start(self):
        self.running = True
        self.worker_thread.start()

    def stop(self):
        self.running = False
