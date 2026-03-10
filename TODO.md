## main todos
- write a short summary about control variables, whether its a problem or not that they're collinear?
- beef up finnish portion of literature review NLP segment
- add wisdom of crowds stuff
- do a quick review of settings for modernbert training

- then move to consructing the sentiment variable
  - models: finbert, modernbert, xlm-roberta, etc.
  - datasets: finnsentiment, financialsentiment and financialphrasbank (translated thru gemini)
  - include some samples how the best model performs on the actual data
  - label sentiment pieces manually, use random sampling until rarest class hits 150 labeled texts

- target + control variable data is ready for now. 
- no need to tinker with it, just focus on constructing sentiment + writing the thesis for now

FIRST THINGS FIRST: download financial phrase bank, finsentiment. then translate them. cook up a training dataset and an evaluation dataset in a separate notebook. 

### PEKKA 3/6 RESPONSE TODOs

#### Literature review
- Laajuus on riittävä, mutta nyt kannattaisi keskittyä enemmän sen perusteella tehtäviin johtopäätöksiin
    - mitä juuri tästä kirjallisuudesta seuraa oman tutkimuksesi asetelmalle
    - miksi tietyt kontrollimuuttujat, viiveet tai estimointimenetelmät ovat perusteltuja
    - mitä aikaisemman kirjallisuuden perusteella pitäisi odottaa (“hypoteesit” / odotukset tuloksista, joihin voi sitten verrata varsinaisia empiirisiä tuloksia)
- NLP-kirjallisuuden osalta riittää, että perustelet, miksi suomenkielinen sijoittajateksti on haastavaa ja miksi sentimentin huolellinen mittaaminen on tarpeen. Tässä ei tarvitse tavoitella liian laajaa benchmark-vertailua.

#### Building the sentiment variable

- Kuvaa mahdollisimman selkeästi mitä dataa käytetään koulutukseen ja mitä arviointiin/testaukseen
- Mitkä mallit/menetelmät sisällytetään vertailuun
- Miten esiprosessointi toteutetaan
- Miten validointi on tarkoitus tehdä ja myös mitä arviointimittareita käytetään (myös kerro millä perusteella lopullinen menetelmä valitaan)
- Tämän osion ei tarvitse kuitenkaan olla kovin massiivinen, riittää että on läpinäkyvä ja vakuuttava tuon päätutkimuskysymyksen kannalta

#### Data and Methodology
- Tämä on ihan hyvällä pohjalla mutta kannattaa vielä lisätä joitakin tarkennuksia mm. miten sisältö yhdistetään yhtiöihin; miten käsitellään päivät jolloin sisältöä ei ole; entä viikonloput ja pörssin kiinnioloajat