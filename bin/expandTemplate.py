"""
Expand templates provconvert style, see usage for further instructions

Author: Doron Goldfarb, Environment Agency Austria
"""


import sys
import prov
import getopt
import json
try:
	from provtemplates import provconv
except ImportError as e:
	try:
		# Try if provconv.py is in current working directory
		sys.path.append('.')
		print ("Error loading provtemplates module with msg \"" + str(e) + "\", trying direct file import from cwd.")
		import provconv
	except ImportError as e2:
		print ("Couldnt load provtemplate lib from file " + str(e2))

def usage():
	print ("Usage:")
	print ("	python expandTemplate.py" )
	print ("	mandatory --infile   = <Template File (PROV-RDF [ttl, trig, xml], PROV-xml, PROV-json)>")
	print ("	-------------------------------------------")
	print ("	mandatory --bindings = <Bindings File (PROV-RDF [ttl, trig, xml], PROV-xml, PROV-json)>")
	print ("	alternat. --bindver3 --bindings=<Bindings File (JSON V3)>")
	print ("	-------------------------------------------")
	print ("		  --outfile  = <Bindings File (PROV-RDF [ttl, trig, xml], PROV-N, PROV-xml, PROV-json)>")
	print ("		  --help  : Show this message")

#make more formats available
#template=prov.model.ProvDocument.deserialize(sys.argv[1], format="rdf", rdf_format="xml")
try:
	opts, args = getopt.getopt(sys.argv[1:], "hi:o:b:v3", ["help", "infile=", "outfile=", "bindings=", "verbose", "bindver3"])
except getopt.GetoptError as err:
	print (str(err))  # will print something like "option -a not recognized"
	usage()
	sys.exit(2)

infile=None
outfile=None
bindings=None
verbose=False
v3=False

for o, a in opts:
	if o == "-v":
		verbose = True
	elif o in ("-h", "--help"):
		usage()
		sys.exit()
	elif o in ("-o", "--outfile"):
		outfile = a
	elif o in ("-i", "--infile"):
		infile = a
	elif o in ("-b", "--bindings"):
		bindings = a
	elif o in ("-3", "--bindver3"):
		v3=True
	else:
		assert False, "unhandled option"

if not infile or not bindings:
	usage()
	sys.exit()

#need to make this better, prov.read does not provide enough error info
template=prov.read(infile)

bindings_dict=None


if v3:
	v3_dict=json.load(open(bindings, "r"))
	bindings=provconv.read_binding_v3(v3_dict)
	bindings_dict=bindings["binddict"]
	bindings_ns=bindings["namespaces"]
	template=provconv.set_namespaces(bindings_ns, template)
else:
	#need to make this better, prov.read does not provide enough error info
	bindings_doc=prov.read(bindings)
	bindings_dict=provconv.read_binding(bindings_doc)
	#print(bindings_doc.namespaces)
	template=provconv.set_namespaces(bindings_doc.namespaces, template)

#print bindings_dict

#print bindings_doc.namespaces

#Add template ns to output doc!!
#print bindings_dict


exp=provconv.instantiate_template(template, bindings_dict)

for s in exp.bundles:
	for r in s.records:
		print (repr(r))

outfilename=outfile
toks=outfilename.split(".")
frmt=toks[len(toks)-1]
if frmt in ["rdf", "xml", "json", "ttl", "trig", "provn"]:
	outfile=open(outfilename, "w")
	if frmt in ["xml", "provn", "json"]:
		outfile.write(exp.serialize(format=frmt))
	else:	
		if frmt == "rdf":
			frmt="xml"
		outfile.write(exp.serialize(format="rdf", rdf_format=frmt))
	outfile.close()

