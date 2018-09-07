# EnvriProvTemplates

This is an implementation of a PROV-Template expander based on the initial work of https://github.com/stephank16 available at https://github.com/stephank16/enes_graph_use_case/tree/master/prov_templates, extended by https://github.com/d0rg0ld


For the specification of PROV-Template see https://provenance.ecs.soton.ac.uk/prov-template/

A more detailed and formal description for the PROV template expansion mechanism is provided in [1]


## Files:

	provconv.py		: 	a library for performing template expansion

	expandTemplate.py	:	a python script using provconv.py to emulate the functionality of provconvert using the -bindings argument

	tests/			:	directory with test files, templates are *.trig, corresponding bindings *.ttl (check matching filenames)

## Sample invocation: 

	python expandTemplate.py --infile tests/template1.trig --bindings tests/binding1.ttl --outfile tests/tb1_exp.provn

## Limitations:

FIXED: ~~The current version has only been tested with python 2.7 and is currently also adapted to python 3~~

### python rdflib releated issues:

	rdflib applies stricter rules regarding IRIs, e.g. local names with leading digits are not allowed there
	see https://github.com/RDFLib/rdflib/issues/742

	If an IRI is provided as prefixed name, there is no problem, i.e.

		@prefix orcid: <http://orcid.org/> 

		... some statement
			tmpl:value_0	orcid:0000-0002-3494-120 .


	But if an IRI is provided in relative or absolute form, i.e

		<http://orcid.org/0000-0002-3494-120X> or <http://orcid.org/0000-0002-3494-120>

	there will be problems if the namespace is not given explicitly

		1) URIs such as <http://orcid.org/0000-0002-3494-120X> will be auto split into weird namespace:localname combinations such as

			@prefix ns1: <http://orcid.org/0000-0002-3494-120> 
			ns1:X

		2) URIs such as <http://orcid.org/0000-0003-0183-6910>  fail completely with an exception "Can't split"

	One possible workaround for such cases has been found to be to explicitly provide the namespaces for those IRIs containing leading digits in their local name, i.e.

	adding  @prefix orcid: <http://orcid.org/> to a bindings file

	is sufficient for rdflib to correctly resolve the above issues.

### Python prov lib related issues

	As for now, the python prov lib can only write provn but not read it. 

## Reference:

[1] L. Moreau, B. V. Batlajery, T. D. Huynh, D. Michaelides, and H. Packer, ‘A Templating System to Generate Provenance’, IEEE Transactions on Software Engineering, vol. 44, no. 2, pp. 103–121, Feb. 2018.

