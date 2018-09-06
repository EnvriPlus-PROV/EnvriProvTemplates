# EnvriProvTemplates

This is an implementation of a PROV-Template expander based on the initial work of https://github.com/stephank16 available at https://github.com/stephank16/enes_graph_use_case/tree/master/prov_templates, extended by https://github.com/d0rg0ld


For the specification of PROV-Template see https://provenance.ecs.soton.ac.uk/prov-template/

A more detailed and formal description for the PROV template expansion mechanism is provided in [1]


Files:
	provconv.py		: 	a library for performing template expansion
	expandTemplate.py	:	a python script using provconv.py to emulate the functionality of provconvert using the -bindings argument
	tests/			:	directory with test files, templates are *.trig, corresponding bindings *.ttl (check matching filenames)

Example invocation: 

	python expandTemplate.py --infile tests/template1.trig --bindings tests/binding1.ttl --outfile tests/tb1_exp.provn

Reference:

[1] L. Moreau, B. V. Batlajery, T. D. Huynh, D. Michaelides, and H. Packer, ‘A Templating System to Generate Provenance’, IEEE Transactions on Software Engineering, vol. 44, no. 2, pp. 103–121, Feb. 2018.

