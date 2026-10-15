import sys
import math


# ============================================
# 🎮 STELLSCHRAUBEN – hier könnt ihr experimentieren!
# ============================================
BREMS_DISTANZ = 900       # Ab welcher Entfernung zum Checkpoint gebremst wird
LANGSAM_SCHUB = 50        # Wie stark gebremst wird (0-100)
SCHARFE_KURVE = 50        # Ab welchem Winkel (Grad) komplett gestoppt wird
MITTLERE_KURVE = 30       # Ab welchem Winkel (Grad) gedrosselt wird
BOOST_DISTANZ = 5000      # Ab welcher Entfernung sich ein Boost lohnt
BOOST_WINKEL = 5          # Boost nur, wenn wir fast gerade auf das Ziel zufahren
# ============================================


boost_verfuegbar = False   # Ab League Wood1: wenn auf True gesetzt: merkt sich, ob wir den Boost schon verbraucht haben


while True:
   x, y, next_checkpoint_x, next_checkpoint_y, next_checkpoint_dist, next_checkpoint_angle = [int(i) for i in input().split()]
   opponent_x, opponent_y = [int(i) for i in input().split()]


   winkel = abs(next_checkpoint_angle)


   # Schub je nach Kurvenwinkel bestimmen
   if winkel > SCHARFE_KURVE:
       schub = 0
   elif winkel > MITTLERE_KURVE:
       schub = LANGSAM_SCHUB
   else:
       schub = 100


   # Vor dem Checkpoint zusätzlich bremsen
   if next_checkpoint_dist < BREMS_DISTANZ:
       schub = min(schub, LANGSAM_SCHUB)


   # Boost einsetzen: nur einmal, nur auf langer, gerader Strecke
   if boost_verfuegbar and next_checkpoint_dist > BOOST_DISTANZ and winkel < BOOST_WINKEL:
       print(f"{next_checkpoint_x} {next_checkpoint_y} BOOST")
       boost_verfuegbar = False
   else:
       print(f"{next_checkpoint_x} {next_checkpoint_y} {schub}")
