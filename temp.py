from __future__ import print_function
import time
import socket
from stem import CircStatus, OperationFailed, InvalidRequest, InvalidArguments, CircuitExtensionFailed
from stem.control import Controller, EventType
import sys
from random import choice
import os
import subprocess
from pprint import pprint 
from numpy import array
import numpy
import inspect
import re
import datetime
import argparse
import traceback
import os.path
from os.path import join, dirname, isfile

sys.path.append(join(dirname(__file__), 'libs'))
from SocksiPy import socks 

version = "1.0"
# Global value of the current circuit ID, to be read by attach_stream
curr_cid = 0
# Global value of 3 circuits constructed, assigned to curr_cid to be constructed
full = 0
sub_one = 0
sub_two = 0

"""
Thrown when destination is not reachable via a public ip address
"""
class NotReachableException(Exception):
	pass

"""
Writes Ting output files
"""
class OutputWriter:
	def __init__(self, args):
		self._controller_port = args['controller_port']
		self._socks_host = '127.0.0.1'
		self._socks_port = args['socks_port']
		self._socks_type = socks.PROXY_TYPE_SOCKS5
		self._buffer_size = args['buffer_size']
		self._destination_ip = args['destination_ip']
		self._destination_port = args['destination_port']
		self._num_tings = args['num_tings']
		self._num_pairs = args['num_pairs']
		self._mode = args['mode']
		self._data_dir = args['data_dir']
		now = datetime.datetime.now()
		self._ting_dir = args['data_dir'] + "tings/" + "{0}_{1}_{2}".format(now.month, now.day, now.year) + "/"
		self._optimize = args['optimize']
		self._current_ting = 1

	def createFile(self):
		current_dir = os.path.dirname(os.path.realpath(__file__))
		first_sub = current_dir + "/" + self._ting_dir
		filenum = 1
		if(not os.path.exists(first_sub)):
			os.makedirs(first_sub)
		else:
			ting_files = os.listdir(first_sub)
			regex = re.compile("ting_\w+_(\d+).txt")
			filenums = []
			for f in ting_files:
				filenums.append(int(regex.findall(f)[0]))
			if not filenums == []:
				filenum = max(filenums)
		self._output_file = self._ting_dir + "/ting_{0}_{1}.txt".format(self._mode,filenum)
		self._f = open(self._output_file, 'a')

		self.writeFileHeader()

	def writeFileHeader(self):
		self._f.write("### Ting " + version + " Log ###\n")
		self._f.write("--------------------------------\n")
		self._f.write("# SOCKS5 port %s\n" % self._socks_port)
		self._f.write("# StemControllerPort %s\n" % self._controller_port)
		self._f.write("# Destination %s:%s\n" % (self._destination_ip,self._destination_port))
		self._f.write("# Source 173.67.5.95 VerizonFIOS Home EllicottCityMD\n")
		self._f.write("# Mode %s\n" % self._mode)
		if(self._optimize):
			self._f.write("# Optimization Caching\n")
		else:
			self._f.write("# Optimization Off\n")
		self._f.write("# BufferSize %s\n" % self._buffer_size)
		self._f.write("# Tings %s\n" % self._num_tings)
		self._f.write("# Pairs %s\n" % self._num_pairs)
		self._f.write("# DataDirectory %s\n" % self._data_dir)
		self._f.write("# DateTime %s\n" % str(datetime.datetime.now()))
		self._f.write("--------------------------------\n")

	# Circuit should be in the form [[fingerprint, ip],[..],...]
	def writeNewCircuit(self, circuit):
		self._f.write("## %s ##\n" % str(self._current_ting))
		self._f.write("--Circuit:\n")
		self._f.write("W %s %s\n" % (circuit[0][0], circuit[0][1]))
		self._f.write("X %s %s\n" % (circuit[1][0], circuit[1][1]))
		self._f.write("Y %s %s\n" % (circuit[2][0], circuit[2][1]))
		self._f.write("Z %s %s\n" % (circuit[3][0], circuit[3][1]))
		self._f.write("--Events:\n")
		self._current_ting += 1

	def writeNewEvent(self, time, pt, relays, data, elapsed):
		event = "{0} [{1} {2}] {3}s\n\t{4}\n".format(time, pt, relays, elapsed, data)
		self._f.write(event)

	def closeFile(self):
		self._f.close()


""" 
Contains all auxillary methods
"""
class TingUtils:
	def __init__(self, data_dir, destination_ip, destination_port, num_tings):
		if(not data_dir[-1] is "/"):
			self._data_dir = data_dir + "/"
		else:
			self._data_dir = data_dir
		self._destination_ip = destination_ip
		self._destination_port = destination_port
		self._num_tings = num_tings
		self.setup_data_dirs()
		
	def setup_data_dirs(self):
		current_dir = os.path.dirname(os.path.realpath(__file__))
		if(not os.path.exists(current_dir + "/" + self._data_dir + "nodes/")):
			os.makedirs(current_dir + "/" + self._data_dir + "nodes/")
		if(not os.path.exists(current_dir + "/" + self._data_dir + "tings/")):
			os.makedirs(current_dir + "/" + self._data_dir + "tings/")

		ip_underscore = self._destination_ip.replace(".", "_")
		now = datetime.datetime.now()
		date_underscore = "{0}_{1}_{2}".format(now.month, now.day, now.year)
		first_sub = current_dir + "/data/nodes/%s" % ip_underscore

		filenum = 1
		if(os.path.exists(first_sub)):
				second_sub = first_sub + "/" + date_underscore
				if(os.path.exists(second_sub)):
					node_files = os.listdir(second_sub)
					regex = re.compile("validexits_\d+_(\d+).txt")
					filenums = []
					for f in node_files:
						if "validexits" in f:
							filenums.append(int(regex.findall(f)[0]))
					if not filenums == []:
						filenum = max(filenums)

		self._valid_exits_fname = "{0}nodes/{1}/{2}/validexits_{3}_{4}.txt".format(self._data_dir, str(ip_underscore), date_underscore, str(self._destination_port), str(filenum))
		self._blacklist_fname = "{0}nodes/{1}/{2}/blacklist_{3}_{4}.txt".format(self._data_dir, str(ip_underscore), date_underscore, str(self._destination_port), str(filenum))

	def make_title(self, socks_port, controller_port, dest_ip, dest_port, mode, mode_args, num_tings, num_pairs, buffer_size, data_dir, optimize):
		print("\n-----------------------------------")
		print("	 _____ _		 \n	|_   _|_|___ ___ \n	  | | | |   | . |\n	  |_| |_|_|_|_  |\n		    |___|")
		print("\n----------- Version 1.0 -----------")
		print("SOCKS Port:", socks_port)
		print("Stem Controller Port:", controller_port)
		print("Destination: {0}:{1}".format(dest_ip, dest_port))
		print(mode, "mode")
		if(optimization):
			print("\tCaching turned on")
		print("Each circuit will transfer {0} {1}-byte packets".format(num_tings, buffer_size))
		if(mode is 'accuracy'):
			print("\tX:", mode_args[0])
			print("\tY:", mode_args[1])
			print(num_pairs, "random pairs of W and Z")
			print("")
		elif(mode is 'check'):
			print("\tX:", mode_args[0])
			print("\tY:", mode_args[1])
		elif(mode is 'random'):
			print("Measuring all {0} combinations of {1} random pairs".format((num_pairs*(num_pairs-1)/2),num_pairs))
		elif(mode is 'rerun'):
			print("Rerunning experiment conducted in: ", mode_args[0])
		print("Data Directory:", data_dir)
		print("-----------------------------------")

	def get_valid_nodes(self):
		exits = {}
		# Open file or generate if it doesn't exist
		try:
			f = open(self._valid_exits_fname)
		except IOError as exc:
			print("Could not find list of valid exit nodes.")
			print("Downloading now... (This may take a few minutes)")
			cmd = ['python', 'scrape_exits.py', '-di', self._destination_ip, '-dp', str(self._destination_port)]
			p = subprocess.Popen(cmd, shell=False)
			p.communicate()
			p.wait()

		f = open(self._valid_exits_fname)
		escapes = ["#", "\t", "\n"]
		for line in f.readlines():
			if(not line[0] in escapes):
				relay = line.strip().replace(" ", "").split(",")
				exits[relay[0]] = relay[1]
		f.close()

		# Remove any blacklisted nodes from exit list
		if(os.path.isfile(self._blacklist_fname)):
			f = open(self._blacklist_fname)
			for line in f.readlines():
				name = line.strip()
				if name in exits:
					del(exits[name])
			f.close()

		self._exits = exits
		return exits

	# Relay should be in ip address form
	def add_to_blacklist(self, relay):
		f = open(self._blacklist_fname, 'a')
		f.write(relay)
		f.write("\n")
		f.close()

		if(relay in self._exits):
			del(self._exits[name])

	# Given a fp, uses standard ping, and returns a 4-element array of the min, avg, max, stddev
	# If any pings timeout, reruns up to five times. After five tries, returns an empty array signaling failure
	def ping(self, fp):
		ip = self._exits[fp]
		pings = []
		attempts = 0
		while((len(pings) < self._num_tings) and attempts < 5):
			attempts += 1
			regex = re.compile("(\d+.\d+) ms")
			cmd = ['ping', '-c', str(self._num_tings), ip]
			p = subprocess.Popen(cmd,stdout=subprocess.PIPE)
			for line in p.stdout.readlines():
				ping = regex.findall(line)
				if ping != [] and "DUP" not in line:
					pings.append(float(ping[0]))
			p.wait()
			pings = pings[:-1]
		return pings

	# Data = string representation of array of pings times
	# Deserializes string into array of floats and returns it
	def deserialize_ping_data(self, data):
		regex = re.compile("(\d+.\d+)")
		temp = regex.findall(data)
		pings = []
		for x in temp:
			pings.append(float(x))
		return pings

	# Computes typical ping stats for a given array of ting times
	def get_stats(self, arr):
		np = array(arr)
		_avg = numpy.mean(np)
		_min = numpy.min(np)
		_max = numpy.max(np)
		_med = numpy.median(np)
		_std = numpy.std(np)
		return [_avg,_min,_max,_med,_std]

	# N - number of relays to pick
	# Existing - list of relays already in the circuit being built
	# Exits - dictionary of valid exit nodes
	def pick_relays(self, n = 4, existing = []):
		relays = [0 for x in range(n)]
		for i in range(len(relays)):
			temp = choice(self._exits.keys())
			while(temp in relays or temp in existing):
				temp = choice(self._exits.keys())
			relays[i] = temp
		return relays

"""
Creates and Modifies Circuits
"""
class CircuitBuilder:
	def __init__(self, controller, utils):
		self._controller = controller
		self._utils = utils

	# Check list of circuits to see if one with the same relays already exists
	def circuit_exists(self, relays):
		for circ in self._controller.get_circuits():
			found = True
			if len(circ.path) == len(relays):
				for i in range(len(circ.path)-1):
					found = circ.path[i][1] == relays[i]
					if i == len(relays)-1:
						break
				if found:
					return circ.id
		return -1

	# If circuit already exists, just return find and return id of it
	def create_circuit(self, relays):
		cid = self.circuit_exists(relays)
		if cid is -1:
			cid = self._controller.new_circuit(relays, await_build = True)
		return cid

	# Builds all necessary circuits for the list of 4 given relays
	# If no relays given, 4 are chosen at random
	# Returns the list of relays used in building circuits
	def build_circuits(self, relays = []):
		while True:
			try:
				if not relays: 
					relays = self._utils.pick_relays()

				global full
				global sub_one
				global sub_two
				full = None
				sub_one = None
				sub_two = None

				full = self.create_circuit(relays)
				sub_one = self.create_circuit(relays[:2])
				sub_two = self.create_circuit(relays[-2:])

				return relays
			except(InvalidRequest, CircuitExtensionFailed) as exc:
				if full is not None:
					self._controller.close_circuit(full)
				if sub_one is not None:
					self._controller.close_circuit(sub_one)
				if sub_two is not None:
					self._controller.close_circuit(sub_two)

"""
Controller class that does all of the work
"""
class Worker:
	def __init__(self, controller, probe_stream, args):
		self._controller = controller
		self._probe_stream = probe_stream
		self._controller_port = args['controller_port']
		self._socks_host = '127.0.0.1'
		self._socks_port = args['socks_port']
		self._socks_type = socks.PROXY_TYPE_SOCKS5
		self._buffer_size = args['buffer_size']
		self._destination_ip = args['destination_ip']
		self._destination_port = args['destination_port']
		self._num_tings = args['num_tings']
		self._num_pairs = args['num_pairs']
		self._mode = args['mode']
		self._data_dir = args['data_dir']
		self._optimize = args['optimize']
		self._verbose = args['verbose']

		self._utils = TingUtils(self._data_dir, self._destination_ip, self._destination_port, self._num_tings)
		self._builder = CircuitBuilder(controller, self._utils)
		self._writer = OutputWriter(args)

	# Tell socks to use tor as a proxy 
	def setup_proxy(self):
	    socks.setdefaultproxy(self._socks_type, self._socks_host, self._socks_port)
	    socket.socket = socks.socksocket
	    sock = socks.socksocket()
	    return sock

	# Run a ping through a Tor circuit, return array of times measured
	def ting(self):
		arr = [0 for x in range(int(self._num_tings))]
		try:
			self._sock.connect((self._destination_ip,self._destination_port))
			msg = "echo " + str(self._num_tings)
			self._sock.send(msg)
			data = self._sock.recv(self._buffer_size)
			if data == "OKAY":
				for i in range(int(self._num_tings)):
					msg = str(time.time())
					print('{0} bytes to {1}: ping_num={2}'.format(self._buffer_size,self._destination_ip,i), end='\r')
					sys.stdout.flush()

					start_time = time.time()
					self._sock.send(msg)
					data = self._sock.recv(self._buffer_size)
					end_time = time.time()

					arr[i] = (end_time-start_time)*1000
			self._sock.close()
			print('Finished {0} pings to {1}'.format(self._num_tings,self._destination_ip))

			return arr
		except TypeError as exc:
			print("Failed to connect using the given circuit.", exc)

	def find_r_xy(self, relays):
		global curr_cid

		count = 0
		r_xd = []
		start = time.time()
		now = datetime.datetime.now()
		while(len(r_xd) != int(self._num_tings)):
			if(count is 3):
				self._utils.add_to_blacklist(self._utils._exits[relays[1]])
				raise NotReachableException
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.connect((self._destination_ip, self._destination_port))
			msg = "ping {0} {1}".format(self._utils._exits[relays[1]], self._num_tings)
			s.send(msg)
			response = s.recv(1024)
			r_xd = self._utils.deserialize_ping_data(response)
			if(len(r_xd) < 1):
				raise NotReachableException
			count = count + 1
		end = time.time()
		elapsed = end - start
		self._writer.writeNewEvent(now, "ping", "X,D", str(r_xd), elapsed)
		if(self._verbose):
			print("RXD: " + str(r_xd))

		count = 0
		r_sy = []
		start = time.time()
		now = datetime.datetime.now()
		while(len(r_sy) != int(self._num_tings)):
			if(count is 3):
				self._utils.add_to_blacklist(self._utils._exits[relays[2]])
				raise NotReachableException

			r_sy = self._utils.ping(relays[2])

			if(len(r_sy) < 1):
				raise NotReachableException

			count = count + 1
		end = time.time()
		elapsed = end - start
		self._writer.writeNewEvent(now, "ping", "S,Y", str(r_sy), elapsed)
		if(self._verbose):
			print("RSY: " + str(r_sy))

        ## PRINT STUFF ABOUT RSY HERE
        # WRITE RSY TO FILE HERE
		circuits = [full, sub_one, sub_two]
		paths = ["S,W,X,Y,Z,D", "S,W,X,D", "S,Y,Z,D"]
		path = 0
		tings = {}
		for cid in circuits:
			curr_cid = cid
			if(self._verbose):
				print("CID: " + cid)
			self._sock = self.setup_proxy()
			start = time.time()
			now = datetime.datetime.now()
			tings[cid] = self.ting()
			self._sock = self._sock.close()
			end = time.time()
			elapsed = end - start
			self._writer.writeNewEvent(now, "ting", paths[path], str(tings[cid]), elapsed)
			path += 1
			if(self._verbose):
				print(tings[cid])
			## PRINT AND WRITE TO FILE

		r_xy = [0 for x in range(int(self._num_tings))]
		for i in range(len(r_xy)):
			r_xy[i] = tings[full][i] - tings[sub_one][i] - tings[sub_two][i] + r_sy[i] + r_xd[i]

		if(self._verbose):
			print ("RXY: " + str(r_xy))
		#stats = self._util.get_stats(r_xy)
		## PRINT AND WRITE TO FILE

	def start(self):

		controller = self._controller
		utils = self._utils
		builder = self._builder
		writer = self._writer

		exits = utils.get_valid_nodes()

		relays = utils.pick_relays()
		writer.createFile()
		circuit = []
		for relay in relays:
			circuit.append([relay, utils._exits[relay]])
		writer.writeNewCircuit(circuit)

		builder.build_circuits(relays)

		controller.add_event_listener(self._probe_stream, EventType.STREAM)

		self.find_r_xy(relays)

		controller.close()
		writer.closeFile()

def main():
	parser = argparse.ArgumentParser(prog='Ting', description='Ting is like ping, but instead measures round-trip times between two indivudal nodes in the Tor network.')
	parser.add_argument('mode', help="Specify running mode.", choices=['accuracy', 'check', 'pairs', 'rerun'], default='pairs')
	parser.add_argument('-n', '--num-pairs', help="Number of pairs to test. Defaults to 100.", default=100)
	parser.add_argument('-dp', '--destination-port', help="Specify destination port.",default=6667)
	parser.add_argument('-di', '--destination-ip', help="Specify destination ip address.", default='128.8.126.92')
	parser.add_argument('-cp', '--controller-port', help="Specify port of Stem controller.", default=9051)
	parser.add_argument('-sp', '--socks-port', help="Specify SOCKS port.", default=9050)
	parser.add_argument('-b', '--buffer-size', help="Specify number of bytes to be sent in each Ting.", default=64)
	parser.add_argument('-p', '--num-tings', help="Specify the number of times to ping each circuit.", default=20)
	parser.add_argument('-d', '--data-dir', help="Specify a different home directory from which to read and write data", default="data/")
	parser.add_argument('-o', '--optimize', help="Cache ping results from S and D to decrease running time", action='store_true')
	parser.add_argument('-v', '--verbose', help="Print all results and stream statuses along the way.", action='store_true')
	args = vars(parser.parse_args())

	controller = Controller.from_port(port = args['controller_port'])
	if not controller:
		sys.stderr.write("ERROR: Couldn't connect to Tor.\n")
		sys.exit
	if not controller.is_authenticated():
		controller.authenticate()
	controller.set_conf("__DisablePredictedCircuits", "1")
	controller.set_conf("__LeaveStreamsUnattached", "1")

	# Attaches a specific circuit to the given stream (event)
	def attach_stream(event):
		try:
			controller.attach_stream(event.id, curr_cid)
		except (OperationFailed, InvalidRequest), error:
			print(traceback.format_exc())
			if str(error) in (('Unknown circuit %s' % curr_cid), "Can't attach stream to non-open origin circuit"):
				print("Attach stream error")
				# If circuit is already closed, close stream too.
				controller.close_stream(event.id)
			else:
				raise

	# An event listener, called whenever StreamEvent status changes
	def probe_stream(event):
		if(args['verbose']):
			print("Probe stream: status={0} purpose={1}".format(event.status, event.purpose))
		if event.status == 'NEW' and event.purpose == 'USER':
			attach_stream(event)

	# Close all non-internal circuits.
	for circ in controller.get_circuits():
		if not circ.build_flags or 'IS_INTERNAL' not in circ.build_flags:
			controller.close_circuit(circ.id)

	w = Worker(controller, probe_stream, args)
	w.start()

	# DON'T FORGET TO CLOSE CONTROLLER!

if __name__ == "__main__":
	main()