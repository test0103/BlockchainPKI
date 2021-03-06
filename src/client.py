from node import Node
from block import Block
from blockchain import Blockchain
from transaction import Transaction
import validator

from Crypto import Random
from Crypto.PublicKey import RSA
from os.path import expanduser
from threading import Thread

import os
import ssl
import json
import time
import errno
import socket
import base64
import pickle

BUFF_SIZE = 2048


class Client(Node):
    def __init__(self, hostname=None, addr="0.0.0.0", port=4848, bind=True, capath="~/.BlockchainPKI/validators/",
                 certfile="~/.BlockchainPKI/rootCA.pem", keyfile="~/.BlockchainPKI/rootCA.key"):
        '''
            :param str name: A canonical name
            :param str addr: The ip address for serving inbound connections
            :param int port: The port for serving inbound connections
            :param str capath:
        '''
        super().__init__(hostname=hostname, addr=addr, port=port,
                         bind=bind, capath=capath, certfile=certfile, keyfile=keyfile)

        self.blockchain = Blockchain()
        self.connections = list()

    def message(self, t):
        '''
            Send a Transaction to the validator network

            :param Transaction t: The transaction to send
        '''
        pass

    def receive(self):
        '''
            Receive incoming connections
        '''
        while True:
            try:
                conn, addr = self.net.accept()
                s = self.receive_context.wrap_socket(conn, server_side=True)
                DATA = bytearray()  # used to store the incoming data
                with s:
                    data = s.recv(BUFF_SIZE)
                    while data:
                        # Continue receiving chunks of the data until the buffer is empty
                        # (until the client sends empty data)
                        DATA += data
                        data = s.recv(BUFF_SIZE)

                    decoded_message = pickle.loads(DATA)
                    #print(decoded_message)
                    if type(decoded_message) == Block:
                        if decoded_message.id > self.blockchain.last_block.id:
                            self.blockchain.chain.append(decoded_message)
            except socket.timeout:
                pass

    def create_connections(self):
        '''
            Create the connection objects from the validators info file and store them as a triple
            arr[0] = hostname, arr[1] = ip, int(arr[2]) = port
        '''
        f = open('../validators_temp.txt', 'r')
        for line in f:
            arr = line.split(' ')
            if self.hostname == arr[0] and self.address == (arr[1], int(arr[2])):
                continue
            else:
                v = validator.Validator(
                    hostname=arr[0], addr=arr[1], port=int(arr[2]), bind=False)
                self.connections.append(v)
        f.close()

    def send_transaction(self, val, tx):
        '''
            Send a transaction to the validator network
            :param Transaction tx: The transaction to send
        '''
        if self.net and self != val:
            # Connect to validators's inbound net using client's outbound net
            address = val.address
            # Serialize the transaction as a bytes object
            txn = pickle.dumps(tx)
            # Create a new socket (the outbound net)
            # print("Attempting to send to %s:%s" % val.address)
            with self.context.wrap_socket(socket.socket(socket.AF_INET, socket.SOCK_STREAM), server_hostname=val.hostname) as s:
                try:
                    # Connect to the validator
                    s.connect(address)
                    # Send the entirety of the message
                    s.sendall(txn)
                except OSError as e:
                    # Except cases for if the send fails
                    if e.errno == errno.ECONNREFUSED:
                        print(e)
                        # return -1, e
                except socket.error as e:
                    print(e)
        else:
            raise Exception(
                "The validator must be initialized and listening for connections")

    def broadcast_transaction(self, tx):
        '''
            Broadcast the creation of a transaction to the network
        '''
        for i in self.connections:
            self.send_transaction(i, tx)

    def update_blockchain(self):
        '''
            Update blockchain to be current
        '''
        block_path = expanduser("~")
        block_path = os.path.join(block_path, ".BlockchainPKI/chain/")
        chain = None
        if os.path.exists(block_path):
            print("Loading local blockchain files...")
            # Need to implement this
        else:
            # Else make the block path and initialize a chain
            # Uncomment next line when serialization is finished
            # os.path.mkdir(block_path)
            chain = Blockchain()
        # Broadcast the last block of our current chain to let the network know we need blocks after this point
        # Uncomment next line before going live
        self.broadcast_transaction(chain.last_block)
        # receive until we are updated ???
        return chain

    def pki_register(self, generator_public_key, name, public_key):
        '''
            Creates a register transaction

            :params: name - name to be associated with public key
                     public_key - the public key to be added
            :return: tx - the transaction that was just generated
        '''
        # input verification
        if len(name) < 1 or len(name) > 255:
            print("The name value must be between 1-255 characters.")
            return -1

        gen, pub = '', ''
        if generator_public_key == public_key:
            temp = self.verify_public_key(open(generator_public_key, 'r'))
            if not temp:
                print("Public key is incorrectly formated. Please try again.")
                return -1
            gen, pub = temp, temp
        else:
            # public key verification
            gen = self.verify_public_key(open(generator_public_key, 'r'))
            if not gen:
                print(
                    "The generator public key is incorrectly formatted. Please try again.")
                return -1

            pub = self.verify_public_key(open(public_key, 'r'))
            if not pub:
                print(
                    "The register public key is incorrectly formatted. Please try again.")
                return -1

        inputs = {"REGISTER": {"name": name, "public_key": pub}}

        # Validate that the name is not already in the blockchain, break if found
        flag = False
        for block in reversed(self.blockchain.chain):
            for tx in block.transactions:
                inp = json.loads(tx.inputs)
                for key in inp.keys():
                    try:
                        if key == "REVOKE":
                            continue
                        if name == inp[key]["name"] or pub == inp[key]["public_key"]:
                            flag = True
                            break
                    except:
                        continue
                if flag == True:
                    break
            if flag == True:
                break

        outputs = dict()
        if flag == False:
            outputs = {"REGISTER": {"success": True}}
        else:
            outputs = {"REGISTER":
                       {"success": False, "message": "This name is already registered."}}

        inputs = json.dumps(inputs)
        outputs = json.dumps(outputs)

        # send the transaction and return it for std.out
        tx = Transaction(transaction_type="Standard",
                         tx_generator_address=gen, inputs=inputs, outputs=outputs)
        # Create an entry point to the validator network that the client can connect to

        # self.broadcast_transaction(tx)
        return tx

    def pki_query(self, generator_public_key, name):
        '''
            Query the blockchain for a public key given a name
        '''
        # input verification
        gen = self.verify_public_key(open(generator_public_key, 'r'))
        if not gen:
            print("The generator public key is incorrectly formatted. Please try again.")
            return -1

        revoke_dict = dict()

        # Query blockchain, break if we find our public key
        public_key = None
        for blk in reversed(self.blockchain.chain):
            for tx in blk.transactions:
                inputs = json.loads(tx.inputs)
                for key in inputs.keys():  # should only be 1 top level key - still O(1)
                    try:
                        if key == "REVOKE":
                            revoke_dict[inputs[key]["name"]] = inputs[key]["public_key"]
                        if name == inputs[key]["name"] and name not in revoke_dict:
                            public_key = inputs[key]["public_key"]
                    except:
                        continue
                if public_key:
                    break
            if public_key:
                break

        inputs = {"QUERY": {"name": name}}

        outputs = dict()
        if public_key:
            outputs = {"QUERY": {"success": True, "public_key": public_key}}
        else:
            outputs = {"QUERY": {"success": False,
                                 "message": "Name not found."}}

        inputs = json.dumps(inputs)
        outputs = json.dumps(outputs)

        tx = Transaction(transaction_type="Standard", tx_generator_address=gen,
                         inputs=inputs, outputs=outputs)

        # self.broadcast_transaction(tx)
        return tx

    def pki_validate(self, generator_public_key, name, public_key):
        '''
            Checks whether the name and public key are valid
            Returns true if it is valid and false if it is not valid
        '''
        gen, pub = '', ''
        if generator_public_key == public_key:
            temp = self.verify_public_key(open(generator_public_key, 'r'))
            if not temp:
                print("Public key is incorrectly formated. Please try again.")
                return -1
            gen, pub = temp, temp
        else:
            gen = self.verify_public_key(open(generator_public_key, 'r'))
            if not gen:
                print(
                    "The generator public key is incorrectly formatted. Please try again.")
                return - 1

            pub = self.verify_public_key(open(public_key, 'r'))
            if not pub:
                print(
                    "The register public key is incorrectly formatted. Please try again.")
                return -1

        if len(name) < 1 or len(name) > 255:
            print("The name value must be between 1-255 characters.")
            return -1

        inputs = {"VALIDATE": {"name": name, "public_key": pub}}

        flag = False
        for blk in reversed(self.blockchain.chain):
            for tx in blk.transactions:
                inp = json.loads(tx.inputs)
                for key in inp.keys():
                    try:
                        if key == "REVOKE":
                            continue
                        if name == inp[key]["name"] and pub == inp[key]["public_key"]:
                            flag = True
                            break
                    except:
                        continue
                if flag == True:
                    break
            if flag == True:
                break

        outputs = dict()
        if flag == True:
            outputs = {"VALIDATE": {"success": True,
                                    "name": name, "public_key": pub}}
        else:
            outputs = {"VALIDATE": {"success": False,
                                    "message": "Cannot validate name and public key"}}

        inputs = json.dumps(inputs)
        outputs = json.dumps(outputs)
        tx = Transaction(
            transaction_type='standard', tx_generator_address=gen, inputs=inputs, outputs=outputs)
        return tx

    def pki_update(self, generator_public_key, name, old_public_key, new_public_key):
        '''
            Updates the public key with the new public key
            Returns the transaction with the new public key
        '''
        # verify the old_public_key
        gen = self.verify_public_key(open(generator_public_key, 'r'))
        if not gen:
            print("The generator public key is not formatted correctly.")
            return -1

        old_key = self.verify_public_key(open(old_public_key, 'r'))
        if not old_key:
            print('This old public key is not formatted correctly')
            return -1
        # verify the new_public_key
        new_key = self.verify_public_key(open(new_public_key, 'r'))
        if not new_key:
            print('This new public key is not formatted correctly')
            return -1

        flag = False
        for block in reversed(self.blockchain.chain):
            for tx in block.transactions:
                inputs = json.loads(tx.inputs)
                for key in inputs.keys():
                    try:
                        if key == "REVOKE":
                            continue
                        if name == inputs[key]['name'] and old_key == inputs[key]['public_key']:
                            flag = True
                    except:
                        continue
                if flag == True:
                    break
            if flag == True:
                break

        # Create the input for the update, for the input we have the name, old_public_key and the new_public_key
        inputs = {"UPDATE": {"name": name,
                             "old_public_key": old_key, "new_public_key": new_key}}

        # Create the output for the update
        outputs = dict()
        if flag == True:
            outputs = {"UPDATE": {"success": True,
                                  "update": True, "new_public_key": new_key}}
        else:
            outputs = {"UPDATE": {"success": False,
                                  "message": "cannot find the name and old public key"}}

        inputs = json.dumps(inputs)
        outputs = json.dumps(outputs)
        tx = Transaction(
            transaction_type='Standard', tx_generator_address=gen, inputs=inputs, outputs=outputs)
        return tx

    def pki_revoke(self, generator_public_key, public_key):
        '''
            Revoke a public key
        '''
        gen, pub = '', ''
        if generator_public_key == public_key:
            temp = self.verify_public_key(open(generator_public_key, 'r'))
            if not temp:
                print("Public key is incorrectly formated. Please try again.")
                return -1
            gen, pub = temp, temp
        else:
            # input verification
            gen = self.verify_public_key(open(generator_public_key, 'r'))
            if not gen:
                print(
                    "The generator public key is incorrectly formatted. Please try again.")
                return -1

            pub = self.verify_public_key(open(public_key, 'r'))
            if not pub:
                print(
                    "The entered public key is incorrectly formatted. Please try again.")
                return -1

        inputs = {"REVOKE": {"public_key": pub}}

        # Query blockchain, break if we find our public key
        flag = False
        for block in reversed(self.blockchain.chain):
            for tx in block.transactions:
                inps = json.loads(tx.inputs)
                for key in inps.keys():  # should only be 1 top level key - still O(1)
                    try:
                        if pub == inps[key]["public_key"]:
                            flag = True
                            break
                    except:
                        continue
                if flag == True:
                    break
            if flag == True:
                break

        outputs = dict()
        if flag == True:
            outputs = {"REVOKE": {"success": True}}
        else:
            # outputs = {"REVOKE": {"success": False,
            #                      "message": "Public key not found."}}
            outputs = {"REVOKE": {"success": False}}

        inputs = json.dumps(inputs)
        outputs = json.dumps(outputs)
        tx = Transaction(transaction_type="Standard", tx_generator_address=gen,
                         inputs=inputs, outputs=outputs)
        return tx

    def print_chain(self):
        for block in reversed(self.blockchain.chain):
            print(block, "\n")

    def command_loop(self):
        # Ensure that the auxillary data folder is set up
        home_path = expanduser("~")
        home_path = os.path.join(home_path, ".BlockchainPKI/")
        if not os.path.exists(home_path):
            os.mkdir(home_path)

        # Finished set up, enter command loop
        print("PKChain Client successfully set up. Type 'help' for a list of commands")
        while True:
            command = input(">>> ").split(" ")
            if command[0] == 'help':
                print("Transactional Functions:\n\n ")
                print(
                    "register                         -Register a name and public key on the blockchain.")
                print(
                    "query                            -Query for a public key given a name.\n\n")
                print(
                    "validate                         -verifies whether a pair of (name, public key) is valid or not")
                print("update                           -Update a user's public key")
                print("Local Functions:\n\n")
                print("chain                          -Print out the current blockchain")
                print(
                    "generate                         -Generate a public and private key pair.")
                print(
                    "encrypt <public_key> <message>   -Encrypt a message with a public key.")
                print(
                    "decrypt <private_key> <message>  -Decrypt a message with a private key.\n\n")
            elif command[0] == 'exit':
                self.close()
                break
            elif command[0] == 'register':
                client_pub_key_path = input(
                    "Enter the path of your public key (generator address): ")
                #client_pub_key = open(client_pub_key_path, 'r')
                name = input(
                    "Enter the name you would like to register to a public key: ")
                reg_pub_key_path = input(
                    "Enter the path of the public key you would like to register: ")
                #reg_pub_key = open(reg_pub_key_path, 'r')
                tx = self.pki_register(
                    client_pub_key_path, name, reg_pub_key_path)
                self.broadcast_transaction(tx)
                print(tx)
            elif command[0] == 'query':
                client_pub_key_path = input(
                    "Enter the path of your public key (generator address): ")
                #client_pub_key = open(client_pub_key_path, 'r')
                name = input("Enter the name you would like to query for: ")
                tx = self.pki_query(client_pub_key_path, name)
                self.broadcast_transaction(tx)
                print(tx)
            elif command[0] == 'validate':
                client_pub_key_path = input(
                    "Enter the path of your public key (generator address): ")
                #client_pub_key = open(client_pub_key_path, 'r')
                name = input("Enter the name you would like to validate: ")
                val_pub_key_path = input(
                    "Enter the path of the public key you would like to validate: ")
                #val_pub_key = open(val_pub_key_path, 'r')
                tx = self.pki_validate(
                    client_pub_key_path, name, val_pub_key_path)
                self.broadcast_transaction(tx)
                print(tx)
            elif command[0] == 'update':
                client_pub_key_path = input(
                    "Enter the path of your public key (generator address): ")
                #client_pub_key = open(client_pub_key_path, 'r')
                name = input(
                    "Enter the name you would like to associate with your updated key: ")
                old_pub_key_path = input(
                    "Enter the path of your old public key: ")
                #old_pub_key = open(old_pub_key_path, 'r')
                new_pub_key_path = input(
                    "Enter the path of your new public key: ")
                #new_pub_key = open(new_pub_key_path, 'r')
                tx = self.pki_update(client_pub_key_path, name,
                                     old_pub_key_path, new_pub_key_path)
                tx_2 = self.pki_revoke(client_pub_key_path, old_pub_key_path)
                self.broadcast_transaction(tx_2)
                self.broadcast_transaction(tx)
                print("Generated two transactions:")
                print(tx_2)
                print(tx)
            elif command[0] == 'revoke':
                client_pub_key_path = input(
                    "Enter the path of your public key (generator address): ")
                #client_pub_key = open(client_pub_key_path, 'r')
                old_pub_key_path = input(
                    "Enter the path of the public key you would like to revoke: ")
                #old_pub_key = open(old_pub_key_path, 'r')
                tx = self.pki_revoke(client_pub_key_path, old_pub_key_path)
                self.broadcast_transaction(tx)
                print(tx)
            elif command[0] == 'generate':
                private_key, public_key = self.generate_keys()
                print()
                print("Your public key is:\n\n",
                      public_key.export_key().decode(), "\n\n")
                print("Your private key is:\n\n",
                      private_key.export_key().decode(), "\n\n")
            elif command[0] == 'chain':
                self.print_chain()
            elif command[0] == 'encrypt':
                print("Implementation coming soon.")
            elif command[0] == 'decrypt':
                print("Implementation coming soon.")
            else:
                print("\nCommand not understood. Type 'help' for a list of commands.\n")

    @staticmethod
    def generate_keys():
        '''
            Generate public and private keys using RSA key generation
        '''
        # Specify the IP size of the key modulus
        modulus_length = 256 * 8
        # Using a Random Number Generator and the modulus length as parameters
        # For the RSA key generation, create your private key
        private_key = RSA.generate(modulus_length, Random.new().read)

        # create the key dir if not created
        home_path = expanduser("~")
        key_path = os.path.join(home_path, ".BlockchainPKI", "keys")
        if not os.path.exists(key_path):
            print("Directory %s does not exist" % key_path)
            cont = input("Would you like to create %s? (y/n): " % key_path)
            if cont.strip() == 'y':
                os.mkdir(key_path)
                print("Created %s" % key_path)

        # write out the private key
        priv_key_name = input(
            "Enter a filename (no extension) for your private key: ")
        file_out = open(os.path.join(key_path, priv_key_name + ".pem"), 'wb')
        file_out.write(private_key.export_key('PEM'))
        print(
            "Sucessfully wrote out new private RSA key to ~/.BlockchainPKI/keys/private.pem")
        file_out.close()

        # write out the public key
        pub_key_name = input(
            "Enter a filename (no extension) for your public key: ")
        file_out = open(os.path.join(key_path, pub_key_name + ".pem"), 'wb')
        file_out.write(private_key.publickey().export_key('PEM'))
        print(
            "Successfully wrote out new public RSA key to ~/.BlockchainPKI/keys/public.pem")
        file_out.close()

        # Generate a public key from the private key we just created
        public_key = private_key.publickey()
        return private_key, public_key

    @staticmethod
    def verify_public_key(public_key):
        '''
            Verify a public key is correctly formatted by making an RSA key object
            :params: public_key - a file object of the public key to be verified
                    passphrase - if the key requires a passphrase use it, otherwise passphrase should be None
        '''
        try:
            key = public_key.read()
            return key
        except ValueError:
            return None


if __name__ == '__main__':
    cli = Client()
    cli.create_connections()
    cli.blockchain = cli.update_blockchain()
    recv = Thread(target=cli.receive)
    recv.start()
    cli.command_loop()
