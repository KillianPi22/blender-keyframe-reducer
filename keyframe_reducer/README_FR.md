# Keyframe Reducer 1.5.0 — version de développement

La version stable publiée reste la 1.1.1. Ce guide décrit le code 1.5.0 non publié,
avec **l'aperçu interactif pour Editable Bezier**.

Add-on gratuit pour Blender 5.2, développé et testé dans Blender **5.2.1 LTS**.
Réduction inspirée du travail avec le Key Reducer de Cinema 4D ; ce n'est pas une
reproduction de son algorithme ni de sa fonction Magnet.

L'interface du plugin est en **anglais** : boutons, options, infobulles et messages.
Ce guide est en français et reprend les libellés anglais exacts.
[English guide](README_EN.md).

## Installation

1. Décompresser le **pack** de livraison.
2. Dans Blender : **Edit > Preferences > Add-ons > menu en haut à droite > Install from Disk**.
3. Sélectionner **keyframe_reducer-1.5.0.zip**, sans décompresser ce ZIP interne.
4. Activer **Keyframe Reducer** si nécessaire.
5. Dans la vue 3D ou le Graph Editor : appuyer sur **N**, puis ouvrir **Key Reducer**.

Blender 5.2.0 minimum. Aucune dépendance, connexion réseau, inscription ou permission spéciale.

Pour mettre à jour une ancienne version : installer le nouveau ZIP au même endroit et
autoriser son remplacement. Enregistrer le projet puis relancer Blender si l'ancienne
interface reste affichée.

## Editable Bezier : moins de contrôles par os, avec des tangentes ajustées

Pour retravailler l'animation, choisir **Tool: Simplify Curve > Curve Style:
Editable Bezier**. Ce mode ajuste les tangentes Bezier en plus de retirer des clés.
Un arc peut ainsi être décrit par quelques contrôles utiles, au lieu de nombreux
points répartis sur la courbe.

1. Sélectionner un ou deux os en Pose Mode, puis une plage représentative de leurs
   points de clés dans le Graph Editor.
2. Cliquer sur **Use Bone Animation Profile**. Ce bouton choisit **Simplify Curve >
   Editable Bezier**, active **Selected Bones Only** et protège les extrema
   significatifs et les poses marquées. Il conserve tes tolérances numériques
   et ne lance pas encore le calcul.
3. Commencer avec **Rotation: 0.5°**. Les limites de position et d'échelle restent
   inchangées ; la position est en unités locales du rig. Une limite plus faible
   conserve davantage de détail de la source.
4. Cliquer sur **Start Interactive Preview**, puis déplacer **Reduction**. Les
   courbes et le compteur se mettent à jour après une courte pause. Comparer
   **Original / Preview**, y compris le mouvement dans la vue 3D.
5. Choisir **Apply Preview** pour retoucher le résultat, ou **Cancel** pour revenir au départ.

### Contrôles interactifs

Reduction multiplie les tolérances de base : avec Rotation à 0,5°, Reduction à
0,5 autorise 0,25°, et Reduction à 2 autorise 1°. Une valeur plus grande permet
généralement moins de clés. Ce n'est ni un nombre de clés cible ni un pourcentage.
Les limites effectives restent visibles ; les limites de base sont dans les
options. Chaque modification repart d'une copie figée de la source et remplace
les demandes de calcul précédentes.

Le dernier résultat terminé reste visible pendant le calcul du suivant. Le
compteur indique alors qu'il s'agit du résultat précédent. **Apply Preview**
n'est disponible que lorsque le réglage actuel est calculé. Les bones et plages
de clés sont capturés au démarrage ; changer la sélection visible ne les étend pas.
Depuis une comparaison manuelle existante, l'aperçu reprend sa plage capturée.
Pour choisir une autre plage, terminer cette comparaison avec Restore Original
ou Keep Copy for Editing, sélectionner la nouvelle plage et relancer l'aperçu.

Cancel restaure l'Action, le slot et la sélection de départ et supprime les copies
temporaires inutilisées. Apply conserve une Action éditable et arrête les mises
à jour. Undo/redo, chargement, désactivation/mise à jour du plugin et sauvegarde
ferment l'aperçu. **Appliquer avant de sauvegarder** : sinon, l'aperçu non appliqué
est annulé et l'Action de départ est sauvegardée. Un aperçu retouché manuellement
est conservé plutôt que supprimé ; appliquer avant de retoucher reste le workflow
normal. Une source modifiée ou un autre objet/Action actif arrête le travail périmé.

Le calcul, l'échantillonnage et l'écriture des courbes avancent par petites étapes
sur le thread principal. Une grosse Action prend encore du temps et la copie,
la vérification ou la suppression de données Blender peut provoquer de courtes
pauses. Il s'agit d'une mise à jour automatique et annulable, pas d'une garantie
de résultat instantané sur un rig complet. Commencer avec un ou deux bones.

**Simplify Selected Keys / Recalculate from Source** restent disponibles pour
un calcul manuel ponctuel, suivi de **Keep Copy for Editing**.

Le panneau affiche **Settings changed: Recalculate** lorsque le résultat visible
correspond aux anciens réglages ou à une autre sélection d'os. Le recalcul reste manuel.

Editable Bezier **reconstruit les tangentes sélectionnées, y compris manuelles**,
et convertit les segments linéaires sélectionnés en Bezier. Les poignées intérieures
sont Aligned, avec une pente commune de chaque côté de la clé. Les extrema importants
et les temps des clés marquées peuvent rester protégés ; les valeurs et temps des
clés restantes sont conservés. Les poignées extérieures aux bornes de la sélection
et le mouvement hors sélection restent intacts.

Le compteur du résultat décrit maintenant les clés réellement concernées après le
filtre par os. Les comptes par courbe et erreurs échantillonnées sont enregistrés
dans `kr_report`, sur l'Action résultat. Le moteur retire les clés devenues inutiles
après ajustement des tangentes et peut remplacer deux clés non protégées par une
clé source mieux placée. Les limites des plateaux guident le premier ajustement.
La détection des extrema suit le sommet principal malgré les petites oscillations.
Chaque proposition est toujours comparée à la courbe d'origine.

À la même tolérance de 0,5°, les essais générés donnent :

| Forme | Editable Bezier 1.3 | Editable Bezier 1.4 |
|---|---:|---:|
| Courbe à épaules de 241 clés | 12 | 9 |
| Transitions rapides de 241 clés | 15 | 10 |
| Mouvement avec longs plateaux de 361 clés | 11 | 6 |
| Arc avec petites oscillations de 361 clés | 12 | 4 |

Ce sont des exemples synthétiques, contrôlés indépendamment tous les seizièmes
d'image. Ils ne valident pas le rig du Minotaure et ne garantissent pas un nombre
minimal de clés. Le résultat Blender est vérifié aux huitièmes de chaque intervalle
source ; en cas d'écart, le moteur réessaie sur ces échantillons plus fins, puis
conserve la source si nécessaire.

Utiliser 0,25° pour davantage de détail, 0,5° comme point de départ, ou 1° si un
écart plus grand convient au mouvement. Ce sont des limites d'erreur angulaire,
pas des garanties de qualité ni un nombre de clés cible. La position dépend des
unités locales du rig. Les oscillations dépassant la limite doivent rester
représentées ; les retirer demanderait davantage de déformation autorisée ou une
opération de lissage distincte. Aucun filtre de lissage n'est appliqué ici.

**Keep Existing Handles** reste le choix par défaut pour préserver le comportement
de la 1.2 : sélectionner explicitement Editable Bezier pour ce nouveau travail.
Ce mode n'ajoute ni lissage, ni filtre Euler, ni verrouillage des contacts en espace
monde. Le recalcul manuel reste synchrone ; l'aperçu interactif produit le même
résultat avec un traitement par étapes. Keep Existing Handles et Key Reducer
conservent leur fonctionnement manuel.

## Simplify Curve : garder les poignées existantes (comportement 1.2)

1. Sélectionner les points des clés de transformation dans le **Graph Editor**.
   Utiliser **A** pour toutes les clés visibles, ou sélectionner plusieurs plages.
2. Dans **N > Key Reducer**, choisir **Tool: Simplify Curve > Curve Style: Keep Existing Handles**.
3. Régler **Allowed Shape Change** : Position / Axis en unités locales du rig,
   Rotation en unités angulaires, Scale / Axis en facteurs d'échelle. Une tolérance
   plus faible conserve davantage de détail. Ce n'est pas un pourcentage de clés à retirer.
4. Garder **Protect Manual Tangents** activé pour protéger les clés Bezier dont
   les poignées sont Free ou Aligned. Le désactiver autorise leur suppression.
5. Cliquer sur **Simplify Selected Keys**, puis comparer **Original / Simplified**.
   Après avoir changé une tolérance, cliquer sur **Recalculate from Source**.
6. Choisir **Keep Copy for Editing** pour poursuivre les corrections, ou **Restore
   Original** pour revenir à la source et fermer la comparaison. Le résultat reste
   disponible dans la liste des Actions pour pouvoir le récupérer.

**Keep Existing Handles** retire les clés redondantes en conservant les valeurs, les temps
et l'interpolation des clés restantes. Les tangentes automatiques intérieures peuvent
être recalculées ; les poignées manuelles restantes sont conservées. Les poignées
des bornes gardent leur position et passent en Free pour protéger le mouvement
voisin. **Key Reducer** conserve sa reconstruction par groupes et son choix de sortie
Bezier / Linear.

Simplify traite toujours les clés sélectionnées, même si la portée de Key Reducer
est Entire Action. Les axes de position, d'échelle et d'Euler sont indépendants,
même avec des plages différentes. Les clés quaternion WXYZ doivent être sélectionnées
ensemble ; l'erreur est alors mesurée sur l'orientation. Strength et le choix
d'interpolation de Key Reducer n'influencent pas Simplify.

Chaque plage exige au moins trois clés consécutives sélectionnées. Les intervalles
non sélectionnés, les clés isolées, les autres canaux et slots, ainsi que la source,
sont préservés. Cette version traite uniquement les transformations ; les propriétés
personnalisées et shape keys ne sont pas prises en charge. Les courbes modifiées,
verrouillées, muettes, échantillonnées ou d'interpolation non prise en charge sont
conservées. La protection des extrema et des clés marquées reste dans les options.

La comparaison mémorise la sélection initiale. **Simplify New Selection** prend
explicitement l'Action affichée comme nouvelle source pour traiter une autre zone.
Changer d'outil ou de portée conserve sinon la source protégée. Le recalcul reste
manuel et remplace les corrections faites sur le résultat : terminer la comparaison
avant d'éditer les clés. La validation échantillonne les courbes locales, y compris
entre les clés ; elle ne garantit pas une erreur continue ou en espace monde.
Cet outil ne lisse pas les tremblements et ne déplace pas les clés dans le temps.

## Correctif 1.1.1 : mise à jour sans mélange de versions

La version 1.1.0 pouvait afficher `Settings.__init__() got an unexpected keyword
argument 'key_selection'` après une installation par-dessus la version 1.0.0 dans
la même session Blender. L'interface était nouvelle, mais le moteur Python restait
chargé en version 1.0.0. La version **1.1.1 recharge les composants dans l'ordre**
lors d'une mise à jour. Le titre du panneau affiche maintenant sa version.

Si tu utilises encore la version 1.1.0 : enregistrer la scène puis fermer complètement
et rouvrir Blender permet aussi de vider l'ancienne version du moteur.
Ce problème ne vient pas de la sélection de clés.

## Nouveau : réduire seulement les clés sélectionnées

1. Dans le **Graph Editor**, afficher les canaux à traiter et sélectionner les
   **points des clés** (par exemple avec **B**, sélection rectangulaire).
2. Dans **N > Key Reducer**, choisir **Scope: Selected Keys**.
3. Régler Strength, puis cliquer sur **Reduce on a Copy**.
4. Comparer **Original / Reduced**. **Recalculate from Source** réutilise la
   sélection mémorisée, même si la sélection visuelle a changé entre-temps.
5. Pour traiter un autre passage, afficher **Reduced**, sélectionner ses clés et
   cliquer sur **Reduce New Selection**. Cette étape prend l'Action
   affichée comme nouvelle source et conserve les réductions déjà affichées.
6. Terminer par **Keep Copy for Editing** avant de corriger les clés.

Chaque suite d'au moins **trois clés consécutives sélectionnées** est traitée
séparément. Une clé non sélectionnée coupe la suite : plusieurs plages peuvent
donc être sélectionnées sans réduire le mouvement entre elles. Les première et
dernière clés de chaque plage sont conservées. Les clés isolées ou les sélections
de deux clés restent intactes.

- Les clés non sélectionnées conservent leurs valeurs, poignées, types et sélection.
  Les poignées des bornes sélectionnées peuvent changer côté intérieur ; leur côté
  extérieur est préservé pour garder le mouvement en dehors de la plage.
- Les canaux masqués ou filtrés du Graph Editor et les canaux verrouillés sont exclus
  de la capture. Sélectionner les points, pas seulement leurs poignées.
- Pour position, échelle et Euler, seuls les axes comportant des clés sélectionnées
  participent. Si plusieurs axes participent, leurs plages doivent avoir des clés
  sélectionnées aux mêmes images ; les clés manquantes coupent la plage commune.
- Pour une **rotation quaternion**, sélectionner **W, X, Y et Z ensemble**, aux mêmes
  images. Une sélection partielle est conservée et signalée dans le panneau.
- Une sélection vide affiche une erreur : elle ne déclenche jamais une réduction
  de toute l'Action. Les propriétés personnalisées ne sont toujours pas réduites.
- La capture initiale et une nouvelle sélection se font depuis le Graph Editor
  en mode **F-Curves**. Une sélection mémorisée peut ensuite être recalculée depuis
  la vue 3D. Le Dope Sheet n'est pas utilisé pour capturer la sélection.

La sélection mémorisée et la comparaison sont conservées dans le fichier .blend.
Changer de portée conserve la source protégée ; **Reduce New Selection** prend
explicitement l'Action affichée comme nouvelle source.

## Utilisation

1. Sélectionner l'armature et son **Action active**, avec le bon slot.
2. Pour un montage NLA complet, effectuer d'abord **Strip > Bake Action** dans le NLA
   (Visual Keying activé, Pose, pas d'écrasement de l'Action), puis désactiver les pistes
   NLA originales. L'add-on réduit une Action, pas directement la pile NLA.
3. Choisir **Scope: Entire Action**, régler **Strength**, puis cliquer sur **Reduce on a Copy**.
4. Lire l'animation et alterner **Original / Reduced** pour comparer.
5. Ajuster Strength ou les tolérances et cliquer sur **Recalculate from Source**.
   Le calcul repart de l'original, sans accumuler les réductions.
6. Cliquer sur **Keep Copy for Editing**, puis corriger les clés dans le Graph Editor.

Les Actions originales et réduites sont conservées à l'enregistrement du .blend.
La réduction n'écrit aucun fichier à votre place. Enregistrer votre projet normalement.
La comparaison reste disponible après sauvegarde et réouverture si l'add-on est activé.
Les modifications manuelles faites à la copie avant **Keep Copy for Editing** sont remplacées lors
du prochain recalcul ; terminer la comparaison avant de retoucher les clés.

## Réglages

| Option | Effet |
|---|---|
| Strength | Multiplie les tolérances. 0,5 conserve davantage de détails ; 1 est le réglage initial ; 2 autorise deux fois plus d'écart. |
| Smooth Bezier | Reconstruit les poignées Auto Clamped, préserve la vitesse aux extrémités, puis contrôle les courbes réellement évaluées par Blender. |
| Linear | Garde une interpolation linéaire, utile pour les données mocap et parfois plus efficace. |
| Position | Écart vectoriel maximal **en unités locales**, avant l'échelle de l'armature. Dans la scène test, le rig est à 0,01 : 0,1 unité locale correspond à environ 0,001 unité monde pour une translation directe. |
| Rotation | Écart angulaire des quaternions ; pour Euler, écart vectoriel des angles non repliés, pour conserver les rotations complètes. Valeur initiale : 0,5°. |
| Scale | Écart vectoriel des facteurs d'échelle ; initialement 0,001. |
| Selected Bones Only | Ne traite que les os sélectionnés en Pose Mode. Aucun effet sur les autres os ni les transformations de l'objet. |
| Keep Significant Extremes | Protège les changements de direction suffisamment marqués des courbes de position, d'échelle et d'Euler. Les quaternions sont protégés par la tolérance angulaire. |
| Protect Extreme / Breakdown Keys | Conserve les images des clés ayant ces types. Utile pour protéger une pose précise. |
| Validate Every 0.25 Frame | Contrôle plus fin ; le réglage normal vérifie toutes les 0,5 image. Les temps des clés sources sont également vérifiés. |

En portée **Entire Action**, les clés sont alignées **par propriété** : XYZ position, XYZ échelle, XYZ Euler ou
WXYZ quaternion. L'add-on ne force pas tous les os ou toutes les propriétés à avoir
leurs poses aux mêmes images ; il ne déplace pas les clés comme Magnet de C4D.

## Protection et limites

- La source est copiée. Les autres slots de l'Action sont conservés tels quels.
- Les propriétés personnalisées, dont `lockInfluenceWeights` de Mixamo, sont conservées.
- Un canal verrouillé, muet, muni de modificateurs ou contenant une interpolation
  constante/spéciale entraîne la conservation de son groupe de transformation.
- Les quaternions incomplets ou avec inversion de signe sont conservés.
- En portée Entire Action, les groupes dont les canaux n'ont pas les mêmes images
  de début/fin sont conservés. En portée Selected Keys, seules les plages
  communes sélectionnées sont traitées.
- Si la reconstruction ne respecte pas la tolérance, le groupe original est restauré.
- Les bornes de chaque groupe et les clés marquées sont conservées. Les clés de sortie
  utilisent les temps des clés existantes ; aucune clé fractionnaire supplémentaire.
- **La vérification porte sur des échantillons de transformations locales**, pas sur une
  garantie continue entre tous les instants, ni sur la position mondiale des pieds.
  Les petites différences de rotation s'accumulent le long de la chaîne du squelette.
  Une correction IK ou des clés de contact peut donc rester nécessaire.
- La réduction n'efface pas automatiquement les tremblements ou les erreurs de mocap.
- Travail sur l'Action active uniquement ; sortir du Tweak Mode avant utilisation.

## Scène test livrée

`TestImportMixamoAnim1_KeyReducer.blend` est une **copie** de la scène fournie.
Le mouvement visible de 1 à 250 a été baké en `KR_Montage_Source`, puis réduit.
Les pistes NLA sont conservées, mais leur évaluation est désactivée sur l'armature
pour ne pas superposer le montage original à son bake. L'Action réduite est active.
Les boutons Original / Reduced permettent de comparer les deux Actions.

Avec Strength 1, rotation 0,5°, Bézier, contrôle toutes les 0,25 image :

| Test | Avant | Après | Réduction |
|---|---:|---:|---:|
| Swing isolé | 38 480 | 14 840 | 61,4 % |
| DropKick isolé | 45 760 | 17 854 | 61,0 % |
| Montage baké 1–250 | 164 750 | 89 062 | 45,9 % |

L'Action déjà éditée `Action` est plus conservatrice : 6 781 → 6 037 clés.
Ses canaux ont souvent des bornes différentes et sont alors laissés intacts.

Le bake reproduit le montage original à environ 0,0000035 unité monde près sur
les positions des os contrôlées à chaque image. Après réduction du montage,
l'écart maximal mesuré est d'environ **0,0138 unité monde**, dont 0,0127 sur
les extrémités mains/pieds. À l'échelle métrique de cette scène, cela correspond
à environ **1,4 cm**. Réduire la tolérance angulaire pour les contacts précis.
Ces mesures décrivent cette scène et ces réglages, pas toutes les animations.

25 contrôles automatiques supplémentaires ont passé : copie intacte, second slot,
clés marquées, alignement XYZ, quaternions, tours Euler, canaux verrouillés,
comparaison, recalcul, nettoyage des anciennes copies inutilisées et échec sans
modification de la source. Les scripts et le rapport sont inclus dans le pack.

La version 1.1.0 ajoute **28 contrôles de sélection** : plages séparées, bornes,
clés non sélectionnées et poignées intactes, axe X seul, quaternions complets ou
partiels, sélection vide, filtres du Graph Editor, panneau latéral, nouvelle
sélection, recalcul et sauvegarde/réouverture. Les 25 contrôles existants passent
également avec cette version. Un test supplémentaire sur l'Action Swing de la
scène Mixamo vérifie la réduction de deux passages sur Hips et LeftForeArm,
avec les autres clés et canaux conservés. Les rapports détaillés sont inclus.

## Code et licence

Le ZIP d'installation contient le code Python intégral et le manifeste Blender.
Licence **GPL-3.0-or-later** ; voir LICENSE. Aucun code de Maxon n'est utilisé.
Cette version n'est affiliée ni à Maxon ni à la Blender Foundation.
