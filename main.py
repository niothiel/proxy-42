import atexit
import logging
import os
import signal
import sys
import threading
import time

import httpproxy
import httpsproxy

try:
  import config
except:
  print 'Unable to read config file!'
  exit(1)

if os.geteuid() != 0:
  print 'You must be running as root for this.'
  exit(1)


def setup_logging():
  rootLogger = logging.getLogger()
  rootLogger.setLevel(logging.DEBUG)

  handler = logging.StreamHandler(sys.stdout)
  handler.setLevel(logging.DEBUG)
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  handler.setFormatter(formatter)
  rootLogger.addHandler(handler)


def build_pf_config(from_http_ports, from_https_ports, to_http_port, to_https_port):
  RDR = 'rdr pass inet proto tcp from any to any port {from_port} -> 127.0.0.1 port {to_port}'
  ROUTE = 'pass out on en0 route-to lo0 inet proto tcp from any to any port {from_port} keep state user != root'

  rdr_http = [RDR.format(from_port=http_port, to_port=to_http_port) for http_port in from_http_ports]
  rdr_https = [RDR.format(from_port=https_port, to_port=to_https_port) for https_port in from_https_ports]

  route_http = [ROUTE.format(from_port=http_port) for http_port in from_http_ports]
  route_https = [ROUTE.format(from_port=https_port) for https_port in from_https_ports]

  return '\n'.join(rdr_http + rdr_https + route_http + route_https)


def enable_pf():
  pf_config = build_pf_config(config.FROM_HTTP_PORTS, config.FROM_HTTPS_PORTS, config.HTTP_LISTEN_PORT, config.HTTPS_LISTEN_PORT)
  shell_command = 'echo "\n{}\n" | pfctl -ef -'.format(pf_config)

  logging.info('About to configure PF with the following value:')
  logging.info(shell_command)

  ret = os.system(shell_command)

  if ret % 256 != 0:
    raise Error('Invalid return code from pfctl')


def disable_pf():
  logging.info('Disabling pf...')
  ret = os.system('pfctl -d')

  if ret % 256 != 0:
    raise Error('Unable to disable pf')


def start_servers():
  httpThread = threading.Thread(target=httpproxy.start_http_proxy, args=(config.PROXY_URL, config.PROXY_PORT, config.PROXY_USERNAME, config.PROXY_PASSWORD, None, config.HTTP_LISTEN_PORT))
  httpThread.daemon = True
  httpThread.start()

  httpsProxy = httpsproxy.HTTPSProxy(config.PROXY_URL, config.PROXY_PORT, config.PROXY_USERNAME, config.PROXY_PASSWORD, None, config.HTTPS_LISTEN_PORT)
  httpsProxy.start()

  while True:
    time.sleep(1)


def exit_handler():
  disable_pf()


if __name__ == '__main__':
  atexit.register(exit_handler)
  setup_logging()
  enable_pf()
  start_servers()