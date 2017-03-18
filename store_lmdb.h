#ifndef _lmdb_store_h_
#define _lmdb_store_h_
#include <stdint.h>
#include <lmdb.h>
#include <sstream>
uint32_t *binary_search(uint32_t what, uint32_t *beg, uint32_t *end);
std::string hexStr(unsigned char* data, int len);

class LMDB_Store {
public:
    LMDB_Store();
    int op_count; //Counter of operations in the current transaction so we commit every now and then
    uint32_t t_idx;

    MDB_env *mdb_env;
    MDB_txn *txn;
    MDB_dbi db_k2t; //Database mapping arbitrary keys to tree number (which is an integer). Allows duplication, sorts the tree numbers.
    MDB_dbi db_f2s; //Database mapping integer (32-bit) keys and tree number (32-bit) as a single DB key
    MDB_dbi db_tdata; //Database storing the full tree data indexed by tree number (32-bit)

    MDB_dbi db_id2c; //Token & tag etc. id to its count
    MDB_dbi db_tk2id; //Token, tag etc into its id

    int open_db(const char *name); //Opens the DB with flags suitable for indexing, etc... Not meant to be general.

    int start_transaction();
    int restart_transaction();
    int finish_indexing();
    int store_tree_flag(unsigned int tree_id, unsigned int flag_number);
    int store_tree_data(unsigned int tree_id, void *t_data, int size);
    int store_key_tree(unsigned int tree_id, void *key_data, int key_size);
    int store_tree_flag_val(unsigned int tree_id, unsigned int key);

    int incerement_a_vocab_item_count(char *key_data, int key_size);
    int store_a_vocab_item(char *key_data, int key_size);
    uint32_t get_id_for(char *key_data, int key_size);


};

#endif
