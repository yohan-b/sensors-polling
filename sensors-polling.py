#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import time
import signal
import yaml
import requests
import subprocess
import argparse
import threading
import socketserver
from http.server import BaseHTTPRequestHandler
from threading import Event
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

parser = argparse.ArgumentParser(description='Sensors polling and metrics recording.')
parser.add_argument("-v", "--verbosity", help="Increase output verbosity",
                    type=str, choices=['DEBUG', 'INFO', 'WARNING'], default='INFO')
args = parser.parse_args()

if args.verbosity == 'DEBUG':
    logging.basicConfig(level=logging.DEBUG)
elif args.verbosity == 'INFO':
    logging.basicConfig(level=logging.INFO)
elif args.verbosity == 'WARNING':
    logging.basicConfig(level=logging.WARNING)

logging.info("====== Starting ======")

stop = Event()
last_data = {}

def handler(signum, frame):
    global stop
    logging.info("Got interrupt: "+str(signum))
    stop.set()
    logging.info("Shutdown")

signal.signal(signal.SIGTERM,handler)
signal.signal(signal.SIGINT,handler)

with open('./conf.yml') as conf:
    yaml_conf = yaml.load(conf)
    polling_conf = yaml_conf.get("polling_conf")
    http_port = yaml_conf.get("http_port")
    default_polling_interval = yaml_conf.get("default_polling_interval")
    default_recording_interval = yaml_conf.get("default_recording_interval")
    max_threads = len(polling_conf)
    recording_api_key = yaml_conf.get("recording_api_key")
    post_url = yaml_conf.get("post_url")

def sensors_polling(poller_conf):
    global stop
    global last_data
    s = requests.Session()
    start_time=time.time()
    last_polling_time=None
    last_recording_time=None
    if 'polling_interval' in poller_conf.keys():
        polling_interval = poller_conf['polling_interval']
    else:
        polling_interval = default_polling_interval

    if 'recording_interval' in poller_conf.keys():
        recording_interval = poller_conf['recording_interval']
    else:
        recording_interval = default_recording_interval

    while True:
        if stop.is_set():
            logging.info('Stopping thread '+poller_conf['name'])
            break
        logging.debug('New while loop for '+poller_conf['name'])
        utc_now = datetime.utcnow()
        now = datetime.now()
        current_time=time.time()

        # Polling
        try:
            logging.debug('Getting data for '+poller_conf['name'])
            command = [poller_conf['executable']] + poller_conf['arguments']
            returned_output = subprocess.check_output(command)
            data = json.loads(returned_output.decode("utf-8"))
            logging.debug('Got: '+returned_output.decode("utf-8"))
            for metric in poller_conf['metrics']:
                last_data[metric['name']] = {'value': data[metric['name']], 'timestamp': utc_now.isoformat()}
            last_polling_time=time.time()
        except Exception as e:
            logging.error(e)
        if last_polling_time is None:
            polling_missed = int((current_time - start_time) // polling_interval)
        else:
            polling_missed = int((current_time - last_polling_time) // polling_interval)
        if polling_missed > 0:
            logging.warning("Missed "+str(polling_missed)+" polling iteration(s)")

        # Recording
        if last_polling_time is not None and (last_recording_time is None or (current_time - last_recording_time > recording_interval and last_polling_time > last_recording_time + recording_interval/2)):
            try:
                for metric in poller_conf['metrics']:
                    logging.debug('Posting data for '+metric['name'])
                    r = s.post(post_url[metric['type']],
                               headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0',
                                        'X-API-KEY': recording_api_key},
                               json={'metric': metric['name'],
                                     'value': last_data[metric['name']]['value'],
                                     'time': utc_now.isoformat()})
                    if r.status_code != 201:
                        logging.error(str(r.status_code)+" "+r.reason)
                last_recording_time=time.time()
            except Exception as e:
                logging.error(e)
        if last_recording_time is None:
            recording_missed = int((current_time - start_time) // recording_interval)
        else:
            recording_missed = int((current_time - last_recording_time) // recording_interval)
        if recording_missed > 0:
            logging.warning("Missed "+str(recording_missed)+" recording iteration(s)")

        # Sleeping
        time_to_sleep = polling_interval - ((current_time - start_time) % polling_interval)
        logging.debug('Sleeping '+str(time_to_sleep)+' seconds for '+poller_conf['name'])
        stop.wait(timeout=time_to_sleep)

def metric_list():
    return([metric['name'] for metric in poller_conf['metrics']])

class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(bytes(str(metric_list())+'\n', 'utf-8'))
        if self.path[1:] in metric_list():
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(bytes(json.dumps(last_data[self.path[1:]])+'\n', 'utf-8'))
        else:
            self.send_response(404)

class WebThread(threading.Thread):
    def run(self):
        httpd.serve_forever()

httpd = socketserver.TCPServer(("", http_port), MyHandler, bind_and_activate=False)
httpd.allow_reuse_address = True
httpd.server_bind()
httpd.server_activate()
webserver_thread = WebThread()
webserver_thread.start()
 
executor = ThreadPoolExecutor(max_workers=max_threads)
threads = []
for poller_conf in polling_conf:
    threads.append(executor.submit(sensors_polling, poller_conf))

logging.info("Polling "+str(metric_list()))

while True:
    if stop.is_set():
        executor.shutdown(wait=True)
        httpd.shutdown()
        httpd.server_close()
        break
    for thread in threads:
        if not thread.running():
            try:
                res = thread.exception(timeout=1)
                if res is not None:
                    logging.error(res)
            except Exception as e:
                logging.error(e)
    stop.wait(timeout=0.5)

logging.info("====== Ended successfully ======")

# vim: set ts=4 sw=4 sts=4 et :
