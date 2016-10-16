#!/usr/bin/env python

import time
import sys
import os

THISDIR=os.path.dirname(os.path.abspath(__file__))
os.chdir(THISDIR)

import subprocess
import cPickle as pickle
import sqlite3
import codecs
from datetime import datetime
from tree import Tree
import re
import zlib
import importlib
import argparse
import db_util
import glob
import tempfile

field_re=re.compile(ur"^(!?)(gov|dep|token|lemma|tag)_(a|s)_(.*)$",re.U)
query_folder = './queries/'


def map_set_id(args, set_dict, set_count):

    just_all_set_ids = []
    optional = []
    types = []

    c_args_s = []
    s_args_s = []
    c_args_m = []
    s_args_m = []

    for arg in args:

        print arg
        compulsory = False
        it_is_set = True

        if arg.startswith('!'):
            compulsory = True    
            narg = arg[1:]
        else:
            narg = arg
        print narg
        optional.append(not compulsory)

        oarg = 0

        if narg.startswith('dep_a'):
            oarg = set_dict['d_' + narg[6:]]
            it_is_set = False
        if narg.startswith('gov_a'):
            oarg = set_dict['g_' + narg[6:]]
            it_is_set = False
        if narg.startswith('lemma_s'):
            oarg = set_dict['l_' + narg[8:]]
            it_is_set = True
        if narg.startswith('token_s'):
            oarg = set_dict['f_' + narg[8:]]
            it_is_set = True
        if narg.startswith('tag_s'):
            it_is_set = True
            if narg[:6] in set_dict.keys():
                oarg = narg[:6]
            else:
                oarg = set_dict['p_' + narg[6:]]
        types.append(not it_is_set)

        #print compulsory
        #print it_is_set
        just_all_set_ids.append(oarg)
        if compulsory:
            if it_is_set:
                c_args_s.append(oarg)
            else:
                c_args_m.append(oarg)
        else:
            if it_is_set:
                s_args_s.append(oarg)
            else:
                s_args_m.append(oarg)


    together = c_args_s + c_args_m

    counts = [set_count[x] for x in together]
    min_c = min(counts)
    rarest = together[counts.index(min_c)]
    print 'optional', optional
    print 'types', types

    return rarest, c_args_s, s_args_s, c_args_m, s_args_m, just_all_set_ids, types, optional 


def query(query_fields):

    print 'qf', query_fields
    """
    query_fields: A list of strings describing the data to fetch
          Each string names a set to retrieve

          (gov|dep)_(a|s)_deptype
          - gov -> retrieve a from-governor-to-dependent mapping/set
          - dep -> retrieve a from-dependent-to-governor mapping/set
          - a -> retrieve a mapping (i.e. used as the third argument of the pairing() function
          - s -> retrieve a set (i.e. the set of governors or dependents of given type)
          - deptype -> deptype or u"anytype"
          prefixed with "!" means that only non-empty sets are of interest

          tag_s_TAG  -> retrieve the token set for a given tag
          prefixed with "!" means that only non-empty sets are of interest

          token_s_WORD -> retrieve the token set for a given token
          lemma_s_WORD -> retrieve the token set for a given lemma
          prefixed with "!" means that only non-empty sets are of interest
    """

    joins=[(u"FROM graph",[])]
    wheres=[]
    args=[]
    selects=[u"graph.graph_id",u"graph.token_count"]
    for i,f in enumerate(query_fields):
        match=field_re.match(f)
        assert match
        req,ftype,stype,res=match.groups() #required? field-type?  set-type?  restriction
        if req==u"!":
            j_type=u""
        elif not req:
            j_type=u"LEFT "
        else:
            assert False #should never happen
        if ftype in (u"gov",u"dep"):
            joins.append((u"%sJOIN rel AS t_%d ON graph.graph_id=t_%d.graph_id and t_%d.dtype=?"%(j_type,i,i,i),[res]))
            if stype==u"s":
                selects.append(u"t_%d.token_%s_set"%(i,ftype))
            elif stype==u"a":
                selects.append(u"t_%d.token_%s_map"%(i,ftype))
        elif ftype in (u"token",u"lemma",u"tag"):
            joins.append((u"%sJOIN %s_index AS t_%d ON graph.graph_id=t_%d.graph_id and t_%d.%s=?"%(j_type,ftype,i,i,i,ftype),[res]))
            selects.append(u"t_%d.token_set"%i)
    
    joins.sort() #This is a horrible hack, but it will sort FROM JOIN ... LEFT JOIN the right way and help the QueryPlan generator
    q=u"SELECT %s"%(u", ".join(selects))
    q+=u"\n"+(u"\n".join(j[0] for j in joins))
    q+=u"\n"
    args=[]
    for j in joins:
        args.extend(j[1])
    return q,args

def get_data_from_db(db_conn,graph_id):
    results=db_conn.execute('SELECT conllu_data_compressed,conllu_comment_compressed FROM graph WHERE graph_id=?',(str(graph_id),))
    for sent,comment in results.fetchall():
        return zlib.decompress(sent).strip(),zlib.decompress(comment).strip()
    return None,None

def load(pyxFile):
    """Loads a search pyx file, returns the module"""
    ###I need to hack around this, because this thing is messing stdout
    print >> sys.stderr, "Loading", pyxFile
    error=subprocess.call(["python","compile_ext.py",pyxFile], stdout=sys.stderr, stderr=sys.stderr)
    if error!=0:
        print >> sys.stderr, "Cannot compile search code, error:",error
        sys.exit(1)
    mod=importlib.import_module(pyxFile)
    return mod

def get_url(comments):
    for c in comments:
        if c.startswith(u"# URL:"):
            return c.split(u":",1)[1].strip()
    return None

def query_from_db(q_obj,db_name,sql_query,sql_args,max_hits,context,set_dict, set_count):
    start = time.time()
    db=db_util.DB()
    db.open_db(unicode(db_name))
    
    rarest, c_args_s, s_args_s, c_args_m, s_args_m, just_all_set_ids, types, optional = map_set_id(query_obj.query_fields, set_dict, set_count)
    db.begin_search(c_args_s, c_args_m, rarest)
    #Filip - not sure what this does
    q_obj.set_db_options(just_all_set_ids, types, optional)


    counter=0
    sql_counter=0

    #print 'MAIN LOOP'
    while True:
        res = query_obj.next_result(db)
        #print ':/'
        if res == -1:
            break
        if len(res) > 0:
            #Oh! We found something!

            #The result set we've got already
            #Okay get the tree text, that's pretty important!
            tree_dict = db.get_tree_text()
            #Get the tree_id
            for r in res:
                print "# visual-style	" + str(r + 1) + "	bgColor:lightgreen"
                #hittoken once the tree is really here!
            #print db.get_current_tree_id()
            print tree_dict
            print 
            
    end = time.time()
    print end- start

    return counter
    
def main(argv):
    global query_obj

    parser = argparse.ArgumentParser(description='Execute a query against the db')
    parser.add_argument('-m', '--max', type=int, default=500, help='Max number of results to return. 0 for all. Default: %(default)d.')
    parser.add_argument('-d', '--database', default="/mnt/ssd/sdata/pb-10M/*.db",help='Name of the database to query or a wildcard of several DBs. Default: %(default)s.')
    parser.add_argument('-o', '--output', default=None, help='Name of file to write to. Default: STDOUT.')
    parser.add_argument('search', nargs="?", default="parsubj",help='The name of the search to run (without .pyx), or a query expression. Default: %(default)s.')
    parser.add_argument('--context', required=False, action="store", default=0, type=int, metavar='N', help='Print the context (+/- N sentences) as comment. Default: %(default)d.')
    parser.add_argument('--keep_query', required=False, action='store_true',default=False, help='Do not delete the compiled query after completing the search.')

    args = parser.parse_args(argv[1:])

    if args.output is not None:
        sys.stdout = open(args.output, 'w')

    if os.path.exists(args.search+".pyx"):
        print >> sys.stderr, "Loading "+args.search+".pyx"
        mod=load(args.search)
    else:
        path = '/'.join(args.database.split('/')[:-1])
        json_filename = path + '/symbols.json' 
        #This is a query, compile first
        import pseudocode_ob_3 as pseudocode_ob

        import hashlib
        m = hashlib.md5()
        m.update(args.search)

        #1. Check if the queries folder has the search
        #2. If not, generate it here and move to the new folder
        try:
            os.mkdir(query_folder)
        except:
            pass

        temp_file_name = 'qry_' + m.hexdigest() + '.pyx'
        if not os.path.isfile(query_folder + temp_file_name):
            f = open('qry_' + m.hexdigest() + '.pyx', 'wt')
            try:
                pseudocode_ob.generate_and_write_search_code_from_expression(args.search, f, json_filename=json_filename)
            except Exception as e:
                os.remove(temp_file_name)
                raise e

            mod=load(temp_file_name[:-4])
            os.rename(temp_file_name, query_folder + temp_file_name)
            os.rename(temp_file_name[:-4] + '.cpp', query_folder + temp_file_name[:-4] + '.cpp')
            os.rename(temp_file_name[:-4] + '.so', query_folder + temp_file_name[:-4] + '.so')

        else:

            os.rename(query_folder + temp_file_name, temp_file_name)

            mod=load(temp_file_name[:-4])            

            os.rename(temp_file_name, query_folder + temp_file_name)
            os.rename(temp_file_name[:-4] + '.cpp', query_folder + temp_file_name[:-4] + '.cpp')
            os.rename(temp_file_name[:-4] + '.so', query_folder + temp_file_name[:-4] + '.so')

    query_obj=mod.GeneratedSearch()
    sql_query,sql_args=query(query_obj.query_fields)
    
    dbs=glob.glob(args.database)
    dbs.sort()

    #hacking and cracking
    
    print 'dbs',dbs
    #dbs = eval(dbs)

    inf = open('set_dict','rb')
    set_dict, set_count = pickle.load(inf)
    inf.close()
    #print set_dict, set_count
    #import pdb;pdb.set_trace()

    total_hits=0
    for d in dbs:
        print >> sys.stderr, 'querying' ,d

        total_hits+=query_from_db(query_obj,d,sql_query,sql_args,args.max,args.context, set_dict, set_count)
        #if total_hits >= args.max and args.max > 0:
        #    break
    print >> sys.stderr, "Total number of hits:",total_hits

    if not args.keep_query:
        try:
            pass
            #os.remove(temp_file_name)
            #os.remove(temp_file_name[:-4] + '.cpp')
            #os.remove(temp_file_name[:-4] + '.so')
        except:
            pass



if __name__=="__main__":
    sys.exit(main(sys.argv))
