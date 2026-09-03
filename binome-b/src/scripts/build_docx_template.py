"""
Construction du gabarit Word utilisé pour l'export des livrables.

Pourquoi un script plutôt qu'un `.docx` déposé à la main : un gabarit binaire ne
se relit pas dans un diff et personne ne peut vérifier d'où viennent ses choix de
mise en forme. Ici, chaque valeur est justifiée en commentaire et le gabarit se
reconstruit par une commande.

**Origine des choix de style.** Ils sont relevés dans
`NetQoS-AI_contrat_interface_final.docx`, le contrat d'interface du Binôme A, qui
sert de référence visuelle au projet :

  - titres en bleu `2E74B5` (accent Word classique) ;
  - Titre 28 pt, Titre 1 16 pt, Titre 2 13 pt ;
  - corps de texte 12 pt ;
  - `Courier New` pour le code ;
  - pied de page paginé, au format « NetQoS-AI — <document> — Page N ».

**Pourquoi ne pas utiliser directement ce fichier comme `--reference-doc`.** Nous
l'avons examiné : son `styles.xml` ne définit que seize styles, ses `docDefaults`
sont vides, et son corps n'utilise en réalité qu'un seul style nommé
(`ListParagraph`) — sa mise en forme est appliquée directement, run par run.
Pandoc, lui, produit des documents stylés par noms (`BodyText`, `VerbatimChar`,
`Table`, `Caption`…). L'employer tel quel priverait donc nos exports du style des
blocs de code, des tableaux et des légendes.

La bonne méthode est celle appliquée ici : partir du gabarit par défaut de pandoc,
qui définit les 49 styles nécessaires, puis y appliquer les conventions visuelles
du document du Binôme A.

Usage (depuis binome-b/) :
    python -m src.scripts.build_docx_template
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

BINOME_B_DIR = Path(__file__).resolve().parent.parent.parent
GABARIT = BINOME_B_DIR / "assets" / "gabarit_netqos.docx"

# --- Conventions relevées dans le document du Binôme A ---
BLEU_TITRES = "2E74B5"
POLICE_CODE = "Courier New"
TAILLES = {"Title": 56, "Heading1": 32, "Heading2": 26, "Heading3": 24, "Heading4": 24}
PIED_DE_PAGE = "NetQoS-AI — Binôme B — Intelligence artificielle & restitution"

FOOTER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:pPr>
      <w:jc w:val="center"/>
      <w:rPr><w:sz w:val="18"/><w:color w:val="666666"/></w:rPr>
    </w:pPr>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="666666"/></w:rPr>
      <w:t xml:space="preserve">{texte} — Page </w:t></w:r>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="666666"/></w:rPr>
      <w:fldChar w:fldCharType="begin"/></w:r>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="666666"/></w:rPr>
      <w:instrText xml:space="preserve">PAGE</w:instrText></w:r>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="666666"/></w:rPr>
      <w:fldChar w:fldCharType="end"/></w:r>
  </w:p>
</w:ftr>
"""


def gabarit_pandoc_brut(destination: Path) -> None:
    """Extrait le gabarit par défaut de pandoc, qui définit tous les styles utiles."""
    if shutil.which("pandoc") is None:
        print("pandoc est introuvable — installation requise.", file=sys.stderr)
        raise SystemExit(1)
    resultat = subprocess.run(
        ["pandoc", "--print-default-data-file", "reference.docx"], capture_output=True
    )
    if resultat.returncode != 0:
        print(f"pandoc a échoué : {resultat.stderr.decode()[:200]}", file=sys.stderr)
        raise SystemExit(1)
    destination.write_bytes(resultat.stdout)


def _appliquer_couleur_et_taille(styles: str) -> str:
    """Colore les titres et fixe leurs tailles, d'après le document du Binôme A."""
    for style_id, taille in TAILLES.items():
        motif = re.compile(
            r'(<w:style [^>]*w:styleId="' + style_id + r'".*?</w:style>)', re.S
        )
        correspondance = motif.search(styles)
        if not correspondance:
            continue
        bloc = correspondance.group(1)

        # Taille : remplacer si présente, insérer sinon.
        if re.search(r"<w:sz w:val=\"\d+\"\s*/>", bloc):
            bloc_modifie = re.sub(
                r"<w:sz w:val=\"\d+\"\s*/>", f'<w:sz w:val="{taille}"/>', bloc, count=1
            )
            bloc_modifie = re.sub(
                r"<w:szCs w:val=\"\d+\"\s*/>", f'<w:szCs w:val="{taille}"/>', bloc_modifie, count=1
            )
        else:
            bloc_modifie = bloc.replace(
                "<w:rPr>", f'<w:rPr><w:sz w:val="{taille}"/><w:szCs w:val="{taille}"/>', 1
            )

        # Couleur : uniquement pour les niveaux de titre, pas pour le Titre principal,
        # que le document de référence laisse en noir.
        if style_id.startswith("Heading"):
            if "<w:color" in bloc_modifie:
                # Remplacer l'élément entier, et non son seul attribut `w:val` :
                # pandoc y joint `w:themeColor` et `w:themeShade`, qui prennent le
                # pas sur la valeur explicite dans Word. Les laisser en place
                # aurait conservé le bleu de pandoc (0F4761).
                bloc_modifie = re.sub(
                    r"<w:color\b[^>]*/>",
                    f'<w:color w:val="{BLEU_TITRES}"/>',
                    bloc_modifie,
                    count=1,
                )
            else:
                bloc_modifie = bloc_modifie.replace(
                    "<w:rPr>", f'<w:rPr><w:color w:val="{BLEU_TITRES}"/>', 1
                )

        styles = styles.replace(bloc, bloc_modifie, 1)
    return styles


def patcher_styles(styles: str) -> str:
    """Applique les conventions du Binôme A au gabarit de pandoc."""
    # Langue française : sans cela Word souligne tout le document en rouge.
    styles = styles.replace('w:val="en-US"', 'w:val="fr-FR"')

    # Police du code : `Courier New` comme dans le document de référence, à la
    # place de `Consolas` retenu par pandoc.
    styles = styles.replace('w:ascii="Consolas"', f'w:ascii="{POLICE_CODE}"')
    styles = styles.replace('w:hAnsi="Consolas"', f'w:hAnsi="{POLICE_CODE}"')

    return _appliquer_couleur_et_taille(styles)


def ajouter_pied_de_page(source: Path, destination: Path) -> None:
    """Réécrit le .docx en y insérant un pied de page paginé.

    Quatre fichiers du paquet OOXML doivent être modifiés de façon cohérente :
    le pied de page lui-même, sa déclaration de type, sa relation avec le
    document, et la référence dans les propriétés de section.
    """
    entree = zipfile.ZipFile(source)
    noms = entree.namelist()

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as sortie:
        for nom in noms:
            contenu = entree.read(nom)

            if nom == "[Content_Types].xml":
                texte = contenu.decode("utf-8")
                if "footer1.xml" not in texte:
                    texte = texte.replace(
                        "</Types>",
                        '<Override PartName="/word/footer1.xml" ContentType='
                        '"application/vnd.openxmlformats-officedocument.'
                        'wordprocessingml.footer+xml"/></Types>',
                    )
                contenu = texte.encode("utf-8")

            elif nom == "word/_rels/document.xml.rels":
                texte = contenu.decode("utf-8")
                if "footer1.xml" not in texte:
                    texte = texte.replace(
                        "</Relationships>",
                        '<Relationship Id="rIdFooterNetQoS" Type="http://schemas.'
                        'openxmlformats.org/officeDocument/2006/relationships/footer" '
                        'Target="footer1.xml"/></Relationships>',
                    )
                contenu = texte.encode("utf-8")

            elif nom == "word/document.xml":
                texte = contenu.decode("utf-8")
                if "rIdFooterNetQoS" not in texte:
                    reference = '<w:footerReference w:type="default" r:id="rIdFooterNetQoS"/>'
                    if "<w:sectPr" in texte:
                        # Le footerReference doit précéder les autres éléments de
                        # sectPr : l'ordre des enfants est imposé par le schéma OOXML.
                        texte = re.sub(
                            r"(<w:sectPr[^>]*>)", r"\1" + reference, texte, count=1
                        )
                    else:
                        texte = texte.replace(
                            "</w:body>", f"<w:sectPr>{reference}</w:sectPr></w:body>"
                        )
                contenu = texte.encode("utf-8")

            elif nom == "word/styles.xml":
                contenu = patcher_styles(contenu.decode("utf-8")).encode("utf-8")

            sortie.writestr(nom, contenu)

        sortie.writestr("word/footer1.xml", FOOTER_XML.format(texte=PIED_DE_PAGE))

    entree.close()


def main() -> None:
    GABARIT.parent.mkdir(parents=True, exist_ok=True)
    brut = GABARIT.parent / "_ref_brut.docx"

    print("Construction du gabarit Word")
    gabarit_pandoc_brut(brut)
    print(f"  gabarit pandoc par défaut extrait ({brut.stat().st_size / 1024:.0f} Ko)")

    ajouter_pied_de_page(brut, GABARIT)
    brut.unlink()

    print(f"  conventions du Binôme A appliquées : titres {BLEU_TITRES}, "
          f"code en {POLICE_CODE}, langue fr-FR, pied de page paginé")
    print(f"\nGabarit écrit : {GABARIT.relative_to(BINOME_B_DIR.parent)} "
          f"({GABARIT.stat().st_size / 1024:.0f} Ko)")
    print("Il est utilisé automatiquement par `python -m src.scripts.export_livrables`.")


if __name__ == "__main__":
    main()
