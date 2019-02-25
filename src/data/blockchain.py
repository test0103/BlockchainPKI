from block_header import Block
import time


class Blockchain:
    difficulty = 3

    def __init__(self):
        self.unconfirm_transactions = []
        self.chain = []
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_block = Block(
            version=0,
            id=0,
            transactions=[],
            previous_hash="0",
            merkle_hash="",
            timestamp=time.time()
            block_generator_address="",
            block_generation_proof="",
            nonce=0,
            status="confirmed",
            t_counter=0
        )
        genesis_block.hash = genesis_block.compute_hash()
        self.chain.append(genesis_block)

    # last_block() returns the last block of the chain
    @property
    def last_block(self):
        return self.chain[-1]

    # Generate a concensus_hash number based on the concensus algorithms
    # This consensus algorithm does not use proof of work
    '''Concensus code go in here...
        def concensus_algorithms(self,...,...)
        ...
        ...
        ...
        return concensus_hash
    '''

    ''' The function to add the new block to the chain after verification that 
        the previous_hash of the new block is poiting to or matched with the hash
        of the previous block (parent block)
        
        + block: a new block mined by the node
        + concensus_hash: the hash of the new block generated by the concensus algorithm.
                          The add_block() also needs to verify that the concensus_hash is match 
                          with the block hash by using the is_valid_concensus_hash(...) method'''

    def add_block(self, block, concensus_hash):
        previous_hash_temp = self.last_block.hash

        # Compare the hash of last block andthe previous_hash of the new block
        if previous_hash_temp != block.previous_hash:
            return False

        if self.is_valid_concensus_hash(block, concensus_hash) != True:
            return False

        block.hash = concensus_hash
        self.chain.append(block)
        return True

    # Validate the concensus_hash of the block and verify if it satisfies
    #  some require criterias (etc. difficulty)

    def is_valid_concensus_hash(self, block, concensus_hash):
        # The 'difficulty' is put here temporary before finding a new way for constraint
        return (concensus_hash.startwith('0' * Blockchain.difficulty) and
                block.compute_hash() == concensus_hash)

    # Add new transaction into the unconfirmed transactions pool
    def add_transactions(self, transaction):
        self.unconfirm_transactions.append(transaction)

    # Mining: add unconfirmed transactions into a block and using the new concensus algorithm to
    # find a new consensus_hash.
    def mine(self):
        if not self.unconfirm_transactions:
            return False

        last_block = self.last_block
        new_block = Block(
            version=last_block.version,
            id=last_block.id + 1,
            transactions=self.unconfirm_transactions,
            previous_hash=last_block.hash,
            merkle_hash=-1,  # Uncertain...
            timestamp=time.time()
            block_generator_address="",
            block_generation_proof="",
            nonce=0,
            status="proposed",
            t_counter=len(self.unconfirm_transactions)
        )

        '''
            ...
            concensus_hash = self.consensus_algorithms(new_block)
            ...
        '''
        self.add_block(new_block, concensus_hash)

        self.unconfirm_transactions = []
        return new_block.id
