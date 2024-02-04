#!/usr/bin/env python
# -*- coding: utf-8 -*-
# # pip install teleinfo
# https://pypi.org/project/teleinfo/
# https://www.magdiblog.fr/gpio/teleinfo-edf-suivi-conso-de-votre-compteur-electrique/

import argparse
import json
from teleinfo import Parser
from teleinfo.hw_vendors import UTInfo2

parser = argparse.ArgumentParser(description='Téléinfo retriever.')
parser.add_argument("-f", "--format", help="Output format.",
                    type=str, choices=['human-readable', 'raw_json', 'custom_json'], default='human-readable')
args = parser.parse_args()

ti = Parser(UTInfo2(port="/dev/ttyUSB0"))
res = ti.get_frame()

if args.format == 'human-readable':
    print "Puissance apparente compteur : "+str(int(res['PAPP']))+"VA"
    # moins précis car Intensité arrondie à l'entier
    print "Puissance apparente calculée : "+str(int(res['IINST'])*230)+"VA"
    print "Puissance souscrite : 6kVA"
    print "Puissance max avant coupure (marge 30%) : 7,8kVA"
    print "Intensité : "+str(int(res['IINST']))+"A"
    print "Intensité abonnement : "+str(int(res['ISOUSC']))+"A"
    print "Consommation : "+str(int(res['BASE']))+"Wh"
elif args.format == 'raw_json':
    print json.dumps(res)
elif args.format == 'custom_json':
    data = {}
    data['Modane_elec_main_power'] = int(res['PAPP'])
    data['Modane_elec_energy_index'] = int(res['BASE'])
    print json.dumps(data)
#for frame in ti:
#  print frame
