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


boost_verfuegbar = False   # Höchstens einmal pro Rennen benutzen!


while True:
   # Kommentare:
   # x und y sind deine Koordinaten.
   # next_checkpoint_x, next_checkpoint_y sind Koordinaten des nächsten Checkpoints
   # next_checkpoint_dist Wie weit wir davon entfernt sind
   # next_checkpoint_angle Winkel zwischen unserer Nase und des nächsten Checkpoints
   
   x, y, next_checkpoint_x, next_checkpoint_y, next_checkpoint_dist, winkel = [abs(int(i)) for i in input().split()]

   # Schub je nach Kurvenwinkel bestimmen
   if winkel > SCHARFE_KURVE:
       schub = 0 # Vollbremsung
   elif winkel > MITTLERE_KURVE:
       schub = LANGSAM_SCHUB
   else:
       schub = 100 # Schneller geht es nicht
   # Vor dem Checkpoint zusätzlich bremsen
   if next_checkpoint_dist < BREMS_DISTANZ:
       schub = min(schub, LANGSAM_SCHUB) # Minimum aus den beiden Variablen

   # Boost einsetzen: nur einmal, nur auf langer, gerader Strecke
   if boost_verfuegbar and next_checkpoint_dist > BOOST_DISTANZ and winkel < BOOST_WINKEL:
       print(next_checkpoint_x, next_checkpoint_y, "BOOST")
       boost_verfuegbar = False # danach ist BOOST verbraucht
   else:
       print(next_checkpoint_x, next_checkpoint_y, schub)
