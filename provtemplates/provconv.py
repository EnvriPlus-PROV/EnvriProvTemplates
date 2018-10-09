'''
a package called provconv to support python based PROV template expansion
  (see: https://ieeexplore.ieee.org/document/7909036/)

see the associated jupyter notebooks for examples and documentation  
  
dependencies: 
    - python prov package (pip installable)
    - python3 (untested for python2)

purpose: a lightweight alternative to the java based ProvToolbox 
         (https://lucmoreau.github.io/ProvToolbox/) 
         for prototyping and for community use cases where the need to
         call an external java executible or an external REST interface 
         (e.g. https://openprovenance.org/services/view/expander )
         is disruptive to the workflow
         
Author: Stephan Kindermann
	Doron Goldfarb

History: 
      - version 0.1    (11. July 2018, Stephan)
        tests based on jinja templates and function based parametrization 
      - version 0.2    (20. July, Stephan)
        redesigned initial version using python prov to generate result instance.
      - version 0.3    (26. July, Stephan) 
        + support for PROV instantiation files 
        + support for multiple entity expansion
      - version 0.4    (27. July)
        + support for attribute attribute expansion
        + support for provdocs without bundles
      - version 0.5    (28. July, Stephan)  
        + bundle support
        + application to concrete ENES use case
      - version 0.6    (28.8.2018, Doron Goldfarb)
	+ support tmpl:linked
	+ support vargen: namespace for auto generated uuids
	+ support expansion for relations (experimental)
        
        
Todo:
      - some more tests
      - later (if time allows): repackage functionality into object oriented 
        programming style with base classes hiding internal functionality 
        (import, export, helper functions for instantiation etc.) and 
        configurable higher level classes ..
        
Package provides:

- instantiate_template(input_template,variable_dictionary) 
  result: instantiated template

- make_binding(prov_doc,entity_dict, attr_dict):
  result: generate a PROV binding document based on an empty input document
     (with namespaces assigned) as well as variable settings for entities and
     attributes (python dictionaries) 
     
'''                        


import prov.model as prov
import prov as provbase
import six      
from six.moves import reduce
import itertools
import uuid
import sys
import collections

#This is the prefix searched for in the passed prov template namespaces in order to identify
#the custom namespace dedicated to vargen identifiers.
#revert to standard uuid: urn:uuid: as default ns
GLOBAL_UUID_DEF_NS_PREFIX="uuid"
GLOBAL_UUID_DEF_NS=prov.Namespace(GLOBAL_UUID_DEF_NS_PREFIX, "urn:uuid:")

class UnknownRelationException(Exception):
	pass

class BindingFileException(Exception):
	pass

class UnboundMandatoryVariableException(Exception):
	pass

class IncorrectNumberOfBindingsForGroupVariable(Exception):
	pass

class IncorrectNumberOfBindingsForStatementVariable(Exception):
	pass

def set_namespaces(ns, prov_doc):
    '''
    set namespaces for a given provenance document (or bundle)
    Args: 
        ns (dict,list): dictionary or list of namespaces
        prov_doc : input document or bundle
    Returns:
        Prov document (or bundle) instance with namespaces set
    '''    
    
 
    if isinstance(ns,dict):  
        for (sn,ln) in ns.items():
    	    #print "Add NS " + sn + " " + ln 
            prov_doc.add_namespace(sn,ln)         
    else:
        for nsi in ns:
    	    #print "Add NS " + repr(nsi)  
            prov_doc.add_namespace(nsi)     
    return prov_doc  

def setEntry(rec, regNS):
	"""
	interpret value provided via v3 bindings, 
	check if qualified name or value, 
	handle datatypes accordingly
	
	Args:
		rec : a key value pair read from v3 bindings file
		regNS: the namespaces read from the context section of the v3 bindings file
	Returns:
		"prov-ified" value, value as-is as fallback	

	#keys:	@id	(for quali)

	#	@type	(for value)
	#	@value	(for value)

	"""

	out=rec
	try:
		if "@id" in rec:
			toks=rec["@id"].split(":")
			#print (repr(toks))
			if len(toks) > 2:
				raise BindingFileException( "Invalid Qualified Name " + rec["@id"] + " found in V3 Json Binding " +  repr(rec))
				#print( "Invalid Qualified Name " + rec["@id"] + " found in V3 Json Binding" )
			#for ns in regNS.get_registered_namespaces():
			for ns in regNS:
				#print (ns)
				if ns.prefix==toks[0]:
					#print ("HIT")
					out=prov.QualifiedName(ns, toks[1])	
		if "@value" in rec:
			if "@type" in rec:
				out=prov.Literal(rec["@value"], datatype=rec["@type"])	
			else:
				out=rec["@value"]
	except:
		raise BindingFileException("Error parsing " + repr(rec))
		#pass
	return out

def read_binding_v3(v3_dict):
	"""
	convert PROV template v3 bindings file to internalt bindings format
	Args:
		v3 bindings json dict 
	Returns:
		internal bindingings dict
	"""
	bindings_dict=dict()
	namespaces=set()
	if "context" in v3_dict:
		#print v3_dict["context"]
		for k in v3_dict["context"]:
			namespaces.add(prov.Namespace(k, v3_dict["context"][k]))	
	if "var" in v3_dict:	
		for v in v3_dict["var"]:
			val=list()
			for rec in v3_dict["var"][v]:
				#print(repr(val))
				val.append(setEntry(rec, namespaces))
			bindings_dict["var:"+v]=val
	if "vargen" in v3_dict:	
		for v in v3_dict["vargen"]:
			val=list()
			for rec in v3_dict["vargen"][v]:
				val.append(setEntry(rec, namespaces))
			bindings_dict["vargen:"+v]=val
	return({ "binddict" : bindings_dict,  "namespaces" : namespaces})	


def read_binding(bindings_doc):
	'''
	read PROV "pre v3" binding file and create dict object

	Args:
		PROV representation of bindings file	
	Return:
		internal bindingings dict
	'''

	#bindings_doc=provbase.read(binding_file)

	binding_dict=dict()

	for r in bindings_doc.records:
		#simple validation: every entity must be in "var", "vargen" namespace
		if r.identifier.namespace.prefix in ["var", "vargen"]:
			#make dicts first
			#we want dumb dicts
			key=r.identifier._str
			binding_dict[key]=dict()
			for a in r.attributes:
				#print str(r.identifier) + "    " + str(a)
				#simple validation: every entity must be in "tmpl" namespace
				if a[0].namespace.prefix in ["tmpl"]:	
					#two cases of bindings, attr and entity
					toks=a[0].localpart.split("_")
					if "2dvalue" == a[0].localpart[:7]:
						if int(toks[1]) not in binding_dict[key]:
							binding_dict[key][int(toks[1])]=dict()
						binding_dict[key][int(toks[1])][int(toks[2])]=a[1]
					elif "value" == a[0].localpart[:5]:
						binding_dict[key][int(toks[1])]=a[1]
					else:
						raise BindingFileException("Encountered unknown property " + str(a) + \
										" in bindings file " + binding_file) 
				else:
					raise BindingFileException("Encountered unknown property " + str(a) + \
										" in bindings file " + binding_file) 
		else:
			raise BindingFileException("Encountered unknown entity ID " + str(r) + \
							" in bindings file " + binding_file + ". Only var: or vargen: allowed as namespace.") 

	#sanity checks: consistent numbering for attrs
	binding_dict_out=dict()


	def checkIdxRange(d):
		# helper function for determining correct numbering of tmpl:value_X and .value_X_Y attrs
		idx=d.keys()
		#print (idx)
		idx=sorted(idx)
		#print (idx)
		#print (min(idx))
		#print (list(range(min(idx), max(idx) + 1)))

		if min(idx) != 0 or idx != list(range(min(idx), max(idx) + 1)):
			raise BindingFileException("Invalid value sequence " + repr(d)  + " encountered in bindings file") 
		return idx


	for b in binding_dict:
		#print repr(b)
		idx=checkIdxRange(binding_dict[b])	
		if not idx:
			return	
		binding_dict_out[b]=list()
		for i in idx:
			if isinstance(binding_dict[b][i], dict):
				subidx=checkIdxRange(binding_dict[b][i])
				if not subidx:
					return
				tmp=list()	
				for i2 in subidx:
					tmp.append(binding_dict[b][i][i2])
				if len(tmp) > 1:
					binding_dict_out[b].append(tmp)
				else:
					binding_dict_out[b].append(tmp[0])
						
			else:
				binding_dict_out[b].append(binding_dict[b][i])
			
	return binding_dict_out
	

def make_binding(prov_doc,entity_dict,attr_dict):
    ''' 
    generate a PROV binding doc from a dict
    
    Args: 
        prov_doc (ProvDocument): input document
        entity_dict (dictionary): entity var settings
             (dict values are lists in case of multiple instantiations)
        attr_dict (dictionary): 
    Returns:
        prov_doc (ProvDocument): prov document defining a PROV binding
        
    '''    
    prov_doc.add_namespace('tmpl','<http://openprovenance.org/tmpl#>')                         
    for var,val in entity_dict.items():
       index = 0 
       if isinstance(val,list): 
           for v in val: 
               prov_doc.entity(var,{'tmpl:value'+"_"+str(index):v})
               index += 1
       else:    
            prov_doc.entity(var,{'tmpl:value':val})

    for var,val in attr_dict.items():
        index = 0
        if isinstance(val,list): 
           for v in val: 
               prov_doc.entity(var,{'tmpl:2dvalue_'+str(index)+'_0':v})
               index +=1
        else:  
               prov_doc.entity(var,{'tmpl:2dvalue_0_0':val})

    return prov_doc

def make_prov(prov_doc): 
    ''' 
    function generating an example prov document for tests and for 
    demonstration in the associated jupyter notebooks
    
    Args: 
        prov_doc (ProvDocument): input prov document with namespaces set
        
    Returns:
        prov_doc (ProvDocument): a valid complete prov document 
        (with namspaces, entities, relations and bundles   
    
    ToDo: 
       for enes data ingest use case: use information from 
       dkrz_forms/config/workflow_steps.py
   
    '''
    bundle = prov_doc.bundle('vargen:bundleid')
    #bundle.set_default_namespace('http://example.org/0/')
    #bundle = prov_doc (for test with doc without bundles)
    quote = bundle.entity('var:quote',(
         ('prov:value','var:value'),
    ))    

    author = bundle.entity('var:author',(
        (prov.PROV_TYPE, "prov:Person"),
        ('foaf:name','var:name')
    )) 

    bundle.wasAttributedTo('var:quote','var:author')
    
    return prov_doc

def save_and_show(doc,filename):
    '''
    Store and show prov document
    
    Args:
        doc (ProvDocument): prov document to store and show
        filename (string) : praefix string for filename
    Returns:
        files stored in different output formats in:
            filename.provn filename.xml, filename.rdf
        prints additionally provn serialization format    
    '''
    doc1 = make_prov(doc)
    #print(doc1.get_provn())

    with open(filename+".provn", 'w') as provn_file:
        provn_file.write(doc1.get_provn())
    with open(filename+".xml",'w') as xml_file:
        xml_file.write(doc1.serialize(format='xml'))
    with open(filename+".rdf",'w') as rdf_file:
        rdf_file.write(doc1.serialize(format='rdf'))    
    
    return doc1

def make_rel(new_entity,rel,ident, formalattrs, otherAttrs):
	"""
	instantiate correct relation type with optional identifier and attributes

	Args: 
		new_entity : Bundle or ProvDoc to be created via template expansion
		rel	:    relation from template to be substituted/expanded
		ident	:    optional identifier for relation, can be None
		formalattrs: ordered list of attribute values to be passed to relation constructor
			     unassigned formal attributes must be part of the list and set to None
			     since order determines semantic of passed values - see legend below
		otherAttrs:  list of (k,v) tuples with optional non-specified attributes for the relation	
	Returns:
		nothing, new rel added to the passed "new_entity" reference	

	# "Legend" for formalattrs, taken from https://www.w3.org/TR/prov-dm/#prov-dm-types-and-relations

	# In the relations below, formalattrs are those parameters between "id;" and ",attrs"

	# id: opt Id
	# c: collection
	# pl: plan
	# t: time

	# e: entity		a: activity			ag: agent
	# e1: entity		a1: activity			ag1: agent
	# e2: entity		a2: activity			ag2: agent
	# alt1: entity		g2: generation activity
	# alt2: entity		u1: usage activity
	# infra: entity
	# supra: entity
	

	#generation	wasGeneratedBy(id;e,a,t,attrs)
	#Usage		used(id;a,e,t,attrs)
	#Communication	wasInformedBy(id;a2,a1,attrs)
	#Start		wasStartedBy(id;a2,e,a1,t,attrs)
	#End		wasEndedBy(id;a2,e,a1,t,attrs)
	#Invalidation	wasInvalidatedBy(id;e,a,t,attrs)
	
	#Derivation	wasDerivedFrom(id; e2, e1, a, g2, u1, attrs)
	
	#Attribution	wasAttributedTo(id;e,ag,attr)
	#Association	wasAssociatedWith(id;a,ag,pl,attrs)
	#Delegation	actedOnBehalfOf(id;ag2,ag1,a,attrs)	
	#Influence	wasInfluencedBy(id;e2,e1,attrs)
	
	#Alternate	alternateOf(alt1, alt2)
	#Specialization	specializationOf(infra, supra)
	
	#Membership	hadMember(c,e)	

	"""
	new_rel=None

	#print (ident)
	#print (formalattrs)

	#handle expansion
	#print (otherAttrs)

	if rel.get_type() == prov.PROV_ATTRIBUTION:
		new_rel = new_entity.wasAttributedTo(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_ASSOCIATION:
		new_rel = new_entity.wasAssociatedWith(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_DERIVATION:
		new_rel = new_entity.wasDerivedFrom(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_DELEGATION:
		new_rel = new_entity.actedOnBehalfOf(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_GENERATION:
		new_rel = new_entity.wasGeneratedBy(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_INFLUENCE:
		new_rel = new_entity.wasInfluencedBy(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_COMMUNICATION:
		new_rel = new_entity.wasInformedBy(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_USAGE:
		new_rel = new_entity.used(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_START:
		new_rel = new_entity.wasStartedBy(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_END:
		new_rel = new_entity.wasEndedBy(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	elif rel.get_type() == prov.PROV_INVALIDATION:
		new_rel = new_entity.wasInvalidatedBy(identifier=ident, other_attributes=otherAttrs, *formalattrs)
	# Thes following guys only have formal attrs
	elif rel.get_type() == prov.PROV_MEMBERSHIP:
		new_rel = new_entity.hadMember(*formalattrs)
	elif rel.get_type() == prov.PROV_ALTERNATE:
		new_rel = new_entity.alternateOf(*formalattrs)
	elif rel.get_type() == prov.PROV_SPECIALIZATION:
		new_rel = new_entity.specializationOf(*formalattrs)
	else:
		raise UnknownRelationException("Relation  " + rel.get_type() + " is not yet supported.")

	

def set_rel(new_entity,rel,idents, expAttr, linkedRelAttrs, otherAttrs):
	'''
	helper function to add specific relations according to relation type
	performs "tmpl:linked" aware expansion and passes relation specific as well as generic attributes

	Args: 
		new_entity : Bundle or ProvDoc to be created via template expansion
		rel	:    relation from template to be substituted/expanded
		idents	:    optional identifier(s) for relation, can be None
		expAttr:     ordered dict of formal attributes to be passed to relation constructor
			     sequence of formal attrs must be provided in order as specified in header of func "make_rel"
		linkedRelAttrs:	attributes grouped by link group, important information for expansion.
		otherAttrs:  list of (k,v) tuples with optional non-specified attributes for the relation	
	Returns:
		None - calls "make_rel" (see above) which instantiates relations in the passed "new_entity"	


	The basic concept of expansion including tmpl:linked is conceived as follows:

	consider all the group level variables (See https://provenance.ecs.soton.ac.uk/prov-template/#dfn-group-variable) 
	assigned to formal relation attributes sorted into groups based on wheter they are defined as linked or not
	If influencer, influencee or secondary vars are in the same link group, there is no cartesian expansion

	example: wasAssociatedWith(id;a,ag,pl,attrs), formal attrs are a(ctivity), ag(ent), pl(an)

	5 modes: 
		1) a linked w. ag linked w. p	-> the variables assigned to these attributes must all have the same number of instances
							which are combined according to their position

		2) a linked with ag, pl not linked -> two of the assigned variables are linked, the third is not, we have
		   a linked with pl, ag not linked    " numInstances(linked var1) == numInstances(linked var2)" 
		   ag linked with pl, a not linked			times 
								"numinstances(unlinked var)" 
									expansions

		3) a, ag and pl are not linked with each other	-> we have numInstances(a) x numInstances(ag) x numInstances(pl) expansions

	''' 

	#check identifier
	# if var: namespace: unbound variable, ignore 
	# if vargen: namespace : create uuid for each ele
	# if not var and not vargen: if same number of idents as elements: iterate, else: fail
	#print idents
	getIdent=False
	makeUUID=False
	if idents:
		if isinstance(idents, list):
			if len(idents) != len(relList):
				raise IncorrectNumberOfBindingsForStatementVariableException("Wrong number of idents for expanded rel " + repr(rel)) 
			getIdent=True
		elif "vargen:" in idents._str and idents._str[:7]=="vargen:":
			#make uuid for each
			makeUUID=True
		elif "var:" in idents._str and idents._str[:4]=="var:":
			#make uuid for each
			idents=None

	#create efficient data structures for expansion with tmpl:linked constraints
	cnt=0
	attrlists=[]
	indexlists=[]
	#separate attribute values by group, but remember their original order in ilist
	attrVisited=[]
	for g in linkedRelAttrs:
		alist=[]
		ilist=[]
		cnt=0
		for a in expAttr:
			if a in g:
				attrVisited.append(a)
				alist.append(expAttr[a])
				ilist.append(cnt)
			cnt+=1
		attrlists.append(alist)
		indexlists.append(ilist)
	
	#Some of the variables were not present in the linked groups.
	if len(attrVisited)!=len(expAttr):
		cnt=0
		for a in expAttr:
			if a not in attrVisited:
				attrlists.append([expAttr[a]])
				indexlists.append([cnt])
				attrVisited.append(a)
			cnt+=1
	
	
	#print (repr(expAttr))
	#print (repr(attrlists))
	#print (repr(indexlists))

	outLists=[]
	# concatenate values in each link group
	for a in attrlists:
		outLists.append(zip(*a))

	#taken from http://code.activestate.com/recipes/577932-flatten-arraytuple/
	flatten = lambda arr: reduce(lambda x, y: ((isinstance(y, (list, tuple)) or x.append(y)) and x.extend(flatten(y))) or x, arr, [])

	#we need this info to maintain the order of formal attributes
	idx=flatten(indexlists)	

	#create cartesian product of grouped variables, this way, only those not in the same group get expanded
	relList=itertools.product(*outLists)

	cnt=0
	#iterate over cartesian product

	#print (repr(relList))

	for element in relList:
		
		#print (element)
		
		out=flatten(element)

		#print (out)

		#reorder based on original ordering
		outordered=[out[i] for i in idx]
		#create expanded relation	
		if getIdent:
			make_rel(new_entity, rel,idents[cnt], outordered, otherAttrs)
		elif makeUUID:
			make_rel(new_entity, rel, prov.QualifiedName(GLOBAL_UUID_DEF_NS, str(uuid.uuid4())), outordered, otherAttrs)
		else:
			make_rel(new_entity, rel,idents, outordered, otherAttrs)
		cnt+=1

def checkLinked(nodes, instance_dict):
	"""
	This function identifies groups of linked variables in the current template

	Arguments:
		nodes:  	List of all variables in the template
		instance_dict:	Lookup table with substitutes from bindings
	Returns:
		dict with following keys:
			"nodes" :	template variables sorted so that each link group 	
				forms a contiguous sequence ordered by 
				"direction" of tmpl:linked, eg for 	

						"var b tmpl:linked to var a 
						 var c tmpl:linked to var b
						 var e tmpl:linked to var d"

				we get the order var a, var b, var c, var d, var e

		"numInstances": the number of instances assigned 
				to each variable in "nodes"
				if vargen vars are linked to regular instantiated vars 
				we create the same number of auto generated instances, 
				they thus get the same number assigned

		"linkedGroups": list of lists each containing the variables 
				belonging to the same link group, ex. above: [[a,b,c], [d,e]]
	
	"""

	"""#we need that for lookup"""
	tmpl_linked_qn=prov.QualifiedName(prov.Namespace("tmpl", "http://openprovenance.org/tmpl#"), "linked")
 
	"""	
	#make tmpl:linked sweep and determine order

	# we essentially create a graph containing all "tmpl:linked" ties and the involved nodes

	# ASSUMPTION: Each entity can only be link to one "ancestor" entity, 
	#			one ancestor entity can be linked to by multiple "successor" entities
	#				NO CYCLES!
	# -> This implies: There is only one root in each link group and 
	#			the network of linked rels is a directed acyclic graph
	"""
	linkedDict=dict()
	linkedGroups=list()
	for rec in nodes:
		eid = rec.identifier
		#print (repr(rec.attributes))
		for attr in rec.attributes: 
			if tmpl_linked_qn == attr[0]:
				linkedDict[eid]=attr[1]
 
	"""# determine order, which of the variables is a "root", i.e only linked to by other vars"""
	dependents=[]
	roots=[]
	intermediates=[]
	for id in linkedDict:
		if id not in dependents:
			dependents.append(id)
	for id in linkedDict:
		if linkedDict[id] not in dependents:
			roots.append(linkedDict[id])
		else:
			intermediates.append(linkedDict[id])

	#print ("roots: " + repr(roots))
	#print ("dependents: " + repr(dependents))
	#print ("intermediates: " + repr(intermediates))

	def dfs_levels(node, links, level):
		"""
		#helper function
		#recursive depth first search to determine order of linked vars	
		"""
		lower=dict()
		#print (str(node) + " " + repr(lower))
		for k in [k for k,v in links.items() if v == node]:
			#print str(k) + " child of " + str(node)
			ret=dfs_levels(k, links, level+1)
			#print repr(ret)
			if ret!=None:
				lower.update(ret)
		myval={node : level}
		#print ("Appending : " + repr(myval))
		lower.update(myval)
	#print ("Returning : " + repr(lower))
		return(lower)

	numInstances=dict()
	combRoot=dict()
	#traverse from root
	offset=0
	for r in roots:
		retval=dfs_levels(r, linkedDict, offset)
		#print ("root: " + str(r))
		#print (retval)
		#get max rank
		maxr=max(retval.values())	

	# we need to check how many entries we have
		maxEntries=0
		for rec in nodes:
			#print (rec)
			if rec.identifier in retval:
				eid = rec.identifier
				neid = match(eid,instance_dict, False)
				#neid = match(eid._str,instance_dict, False)
				#assume single instance bound to this node
				length=0
				if not isinstance(neid, list):
					length=1
				#print (repr(neid))
				#print (repr(eid))
			#if neid==eid._str:
				if neid==eid:
					#no match: if unassigned var or vargen variable, assume length 0
					length=0
					#print("same")
				if length>maxEntries:
					maxEntries=length
			#print neid
				if isinstance(neid,list):
					#list is assigned to node, now all lengths must be equal
					length=len(neid)
					if length!=maxEntries:
						if maxEntries>0:
							#print (length)
							#print (maxEntries)
							raise IncorrectNumberOfBindingsForGroupVariable("Linked entities must have same number of bound instances!")
						maxEntries=length
			#	print (length)

		for n in retval:
			numInstances[n]=maxEntries
		combRoot.update(retval)
		linkedGroups.append(retval)
		offset=maxr+1

	for rec in nodes:
		if rec.identifier not in combRoot:
			combRoot[rec.identifier]=offset
			linkedGroups.append({rec.identifier : offset})
			eid=rec.identifier
			neid = match(eid._str,instance_dict, False)
			if isinstance(neid, list):
				numInstances[eid]=len(neid)
			else:
				numInstances[eid]=1
		#need to remember number of instances for each var
		# when multiple link groups rank accordingly

	#print (repr(combRoot))
	#try reorder nodes based on tmpl:linked hierarchy	
	#nodes_sorted=sorted(nodes, key=retval.get)  

	fnc=lambda x: combRoot[x.identifier]
	nodes_sorted=sorted(nodes, key=fnc)
	#for rec in nodes_sorted:
		#print ("SORT : " + str(rec.identifier))

	#print (repr(linkedGroups))

	return { "nodes" : nodes_sorted, "numInstances" : numInstances, "linkedGroups" : linkedGroups}


def prop_select(props,n):
	'''
	helper function to select individual values if dict value is a list
	'''
	nprops = {}
	#print("Props and n: ",props,n)
	for key,val in props.items():
		if isinstance(val,list):
			#print ("---------------")
			#print (len(val))
			#
			#BRUTE FORCE
			#print (n)
			#BRUTE FORCE
			if len(val)==1:
				n=0
			if n >= len(val):
				raise IncorrectNumberOfBindingsForStatementVariable("Attribute " + str(key) + " has incorrect number of bindings.")
			nprops[key] = val[n]
		else:
			nprops[key] = val 
	return nprops        

def add_records(old_entity, new_entity, instance_dict):
	'''
	function adding instantiated records (entities and relations) to a 
	prov document and containing bundles
	
	calls the match() and attr_match() functions for the instantiation
	
	Args:
	old_entity (bundle or ProvDocument): Prov template for structre info
	
	new_entity (bundle or ProvDocument): Instantiated entity with matched 
	records (entities and relations)
	
	instance_dict: Instantiation dictionary   
	Returns:   
	new_entity (bundle or ProvDocument): Instantiated entity
	
	Todo: change return values of functions (this one and the ones called)    
	
	'''
	
	#print("Here add recs")
	
	relations = []
	nodes = []
	
	# for late use:
	# node_label = six.text_type(record.identifier)
	# uri = record.identifier.uri
	# uri = qname.uri
	
	for rec in old_entity.records:
		if rec.is_element():
			nodes.append(rec)
			#print(rec)
		elif rec.is_relation():
			relations.append(rec)
		else:
			print("Warning: Unrecognized element type: ",rec)

	linkedInfo=checkLinked(nodes, instance_dict)
	nodes_sorted=linkedInfo["nodes"]
	numInstances=linkedInfo["numInstances"]
	linkedGroups=linkedInfo["linkedGroups"]

	for rec in nodes_sorted:
		eid = rec.identifier
		attr = rec.attributes
		args = rec.args
		#print(attr)
		
		#print eid._str
		#dirty trick
		neid = match(eid._str,instance_dict, True, numInstances[eid])
		#print repr(neid)
		#print repr(eid)
		
		#IF no match found then this var is unbound. In case of entities, this is always an error according to
		# https://provenance.ecs.soton.ac.uk/prov-template/#errors

		if neid == eid._str:
			if "var:" in eid._str and eid._str[:4]=="var:":
				raise UnboundMandatoryVariableException("Variable " + eid._str + " at mandatory position is unbound.")


		#print(repr(instance_dict))
		props_raw = attr_match(attr,instance_dict)
		props=dict()
		#eliminate tmpl:linked
		for p in props_raw:
			if "tmpl:linked"!=p._str:
				props[p]=props_raw[p]
	
		"""	
		print ("-------------------")
		print (repr(rec))
		print (rec)
		print (rec.get_asserted_types())
		print (rec.get_type())
		print ("######################")
		print (repr(eid))
		print (repr(neid))
		print (repr(props))
		print (repr(args))
		print ("-------------------")
		"""
		#here we cann inject vargen things if there is a linked attr 


		if isinstance(neid,list):
			i = 0
			for n in neid: 
				oa=prop_select(props,i)
				#print (repr(oa))
				otherAttr=list()
				for ea1 in oa:
					#print (ea1)
					#ea1_match=match(ea1[1], instance_dict, False)
					if isinstance(oa[ea1], list):
						for a in oa[ea1]:
							otherAttr.append(tuple([ea1, a]))
					else:
						otherAttr.append(tuple([ea1, oa[ea1]]))
			#print (n)
				newRec=prov.ProvRecord(rec.bundle, n,attributes=otherAttr)
				newRec._prov_type=rec.get_type()
				#print (newRec)
				new_node = new_entity.add_record(newRec)
				#new_node = new_entity.entity(prov.Identifier(n),other_attributes=prop_select(props,i))
				i += 1
		else:
			#print (eid)
			#print (repr(neid))
			#print (instance_dict)
			#print (numInstances)
			#print (linkedGroups)
			#print (repr(props))
			newprop=list()
			for p in props:
				if isinstance(props[p], list):
					for a in props[p]:
						newprop.append(tuple([p, a]))
				else:
					newprop.append(tuple([p, props[p]]))
			print (repr(newprop))
			print (rec.bundle)
			print (prov.Identifier(neid))
			
			newRec=prov.ProvRecord(rec.bundle, prov.Identifier(neid),attributes=newprop)
			newRec._prov_type=rec.get_type()
			print (newRec)
			new_node = new_entity.add_record(newRec)
			#new_node = new_entity.entity(prov.Identifier(neid),other_attributes=props)

	for rel in relations:
		#print (rel)

		#translate any tmpl entries
		

		#print (repr(rel))
		#print (repr(rel.attributes))
	
		#expand all possible formal attributes
		linkedMatrix=collections.OrderedDict()
		expAttr=collections.OrderedDict()

		

		for fa1 in rel.formal_attributes:
			linkedMatrix[fa1[0]]=collections.OrderedDict()
			for fa2 in rel.formal_attributes:
				linkedMatrix[fa1[0]][fa2[0]]=False
				for group in linkedGroups:
					if fa1[1] in group and fa2[1] in group: 
						linkedMatrix[fa1[0]][fa2[0]]=True	
			if fa1[1] != None:
				expAttr[fa1[0]]=match(fa1[1], instance_dict, False)
				if not isinstance(expAttr[fa1[0]], list):
					expAttr[fa1[0]]=[expAttr[fa1[0]]]
			else:
				#SPECUIAL CASE: prov:timea
				if fa1[0]._str=="prov:time":
					expAttr[fa1[0]]=[None]
					for ea1 in rel.extra_attributes:
						if ea1[0]._str=="tmpl:time":
							expAttr[fa1[0]]=match(ea1[1], instance_dict, False) 
							if not isinstance(expAttr[fa1[0]], list):
								expAttr[fa1[0]]=[expAttr[fa1[0]]]
							
				else:
					expAttr[fa1[0]]=[None]

		#dont forget extra attrs. these are not expanded but taken as is.
		
		
		#we also want grouped relation attribute names
		linkedRelAttrs=[]
		for group in linkedGroups:
			lst=[]
			for fa1 in rel.formal_attributes:
				if fa1[1] in group:
					lst.append(fa1[0])
			if len(lst)>0:
				linkedRelAttrs.append(lst)
		

		#print repr(linkedRelAttrs)

		args = rel.args

		linked=False
		for group in linkedGroups:
			#print "IS " + str(args[0]) + " linked with  " + str(args[1])
			if args[0] in group and args[1] in group:
				#print repr(group)
				#print str(args[0]) + " linked with  " + str(args[1])
				linked=True
				break

		(nfirst,nsecond) = (match(args[0],instance_dict, False),match(args[1],instance_dict, False))     


	#dont forget extra attrs
		otherAttr=list()
		for ea1 in rel.extra_attributes:
			if ea1[0]._str != "tmpl:time":
				ea1_match=match(ea1[1], instance_dict, False)
				if isinstance(ea1_match, list):
					for a in ea1_match:
						otherAttr.append(tuple([ea1[0], a]))
				else:
					otherAttr.append(tuple([ea1[0], ea1_match]))
		
		idents=match(rel.identifier, instance_dict, False)

		#We need to check if instances are linked    
		new_rel = set_rel(new_entity,rel,idents, expAttr,linkedRelAttrs, otherAttr)        
		#new_rel = set_rel_o(new_entity,rel,nfirst,nsecond, linked)        
	return new_entity   


def match(eid,mdict, node, numEntries=1):
	'''
	helper function to match strings based on dictionary
	
	Args:
		eid (string): input string
		mdict (dict): match dictionary
	Returns:
		meid: same as input or matching value for eid key in mdict
	'''
	adr=eid
	if isinstance(adr,prov.QualifiedName):
		lp = adr.localpart
		ns = adr.namespace.prefix
		adr=ns+":"+lp
	#override: vargen found in entity declaration position: create a uuid
	#print ("match " + repr(adr) + " with " + str(adr) + " red " + str(adr)[:7])
	#not optimal, need ability to provide custom namespace

	# FIX NAMESPACE FOR UUID!!!!!!!!

	if node and "vargen:" in str(adr) and str(adr)[:7]=="vargen:":
		ret=None
		for e in range(0,numEntries):
			uid=str(uuid.uuid4())
			if adr not in mdict:
				ret=prov.QualifiedName(GLOBAL_UUID_DEF_NS, uid)
				mdict[adr]=ret
			else:
				if not isinstance(mdict[adr], list):
					tmp=list()
					tmp.append(mdict[adr])
					mdict[adr]=tmp
					tmp2=list()
					tmp2.append(ret)
					ret=tmp2
				qn=prov.QualifiedName(GLOBAL_UUID_DEF_NS, uid)
				mdict[adr].append(qn)
				ret.append(qn)
		return ret
	if adr in mdict:
		#print("Match: ",adr)
		madr = mdict[adr]
	else:
		#print("No Match: ",adr)
		madr = eid 
	return madr

def attr_match(attr_list,mdict):
	'''
	helper function to match a tuple list
	Args:
		attr_list (list): list of qualified name tuples
		mdict (dict): matching dictionary

	ToDo: improve attr_match and match first version helper functions    


		#TO DO: STARTTIME ENDTIME TIME

	'''      
	p_dict = {}
	for (pn,pv)  in attr_list:
		#print ("pn: " + repr(pn) + " pv: " + repr(pv))
		npn_new = match(pn,mdict, False)
		#for now, only take first list ele if npn_mew is list
		#print ("npn_new: " + repr(npn_new))
		if isinstance(npn_new, list):
			npn_new=npn_new[0]
		#print ("npn_new: " + repr(npn_new))
		res=match(pv,mdict, False)
		#print ("res: " + repr(res))
		p_dict[npn_new] = res
		#print("Attr dict:",p_dict)
	return p_dict 
#---------------------------------------------------------------

def instantiate_template(prov_doc,instance_dict):
	global GLOBAL_UUID_DEF_NS
	'''
	Instantiate a prov template based on a dictionary setting for
	the prov template variables
	
	Supported:
		entity and attribute var: matching
		multiple entity expansion

	Unsupported by now:
		linked entities
		multiple attribute expansion

	To Do: Handle core template expansion rules as described in
		https://ieeexplore.ieee.org/document/7909036/ 
		and maybe add additional expansion/composition rules for
		templates useful to compose ENES community workflow templates

	Args: 
		prov_doc (ProvDocument): input prov document template
		instance_dict (dict): match dictionary
	''' 

	#print("here inst templ")


	#instance dict override: replace tmpl:startTime and tmpl:endTime with prov:startTime and prov:endTime
	instance_dict["tmpl:startTime"]=prov.QualifiedName(prov.Namespace("prov", "http://www.w3.org/ns/prov#"),"startTime")
	instance_dict["tmpl:endTime"]=prov.QualifiedName(prov.Namespace("prov", "http://www.w3.org/ns/prov#"),"endTime")
	instance_dict["tmpl:time"]=prov.QualifiedName(prov.Namespace("prov", "http://www.w3.org/ns/prov#"), "time")

	#print repr(instance_dict)

	#CHECK FOR NAMESPACE FOR VARGEN UUID
	for ns in prov_doc.namespaces:
		if ns.prefix==GLOBAL_UUID_DEF_NS_PREFIX:
			#print ("found namespace")
			#uuid namespace defined in template? Use this one
			GLOBAL_UUID_DEF_NS=ns

	new_doc = set_namespaces(prov_doc.namespaces,prov.ProvDocument()) 

	
	new_doc = add_records(prov_doc,new_doc,instance_dict)

	blist = list(prov_doc.bundles)

	#print (repr(blist))
	#print ("iterating bundles")
	for bundle in blist:       
		id1=match(bundle.identifier, instance_dict, True)
		#print (id1)
		#print (repr(id1))
		#print ("---")
		new_bundle = new_doc.bundle(id1)   
		#print (repr(new_bundle))
		new_bundle = add_records(bundle, new_bundle,instance_dict)      

	return new_doc
