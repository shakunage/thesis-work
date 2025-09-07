NAME: FinnSentiment 1.1, source
LICENSE: This corpus is licensed with CC BY 4.0

For more information see http://urn.fi/urn:nbn:fi:lb-2023012701

FinnSentiment is a Finnish social media corpus for sentiment polarity annotation. 27,000 sentence data set annotated independently with sentiment polarity by three native annotators.

The creation of the corpus is documented in K. Lindén, T. Jauhiainen, S. Hardwick (2023): FinnSentiment - A Finnish Social Media Corpus for Sentiment Polarity Annotation. Language Resources and Evaluation 2023.

This is a supplementary release containing additional re-annotations done by the authors of the article.

The corpus is available in a utf-8 encoded TSV (tab-separated values) file with columns as indicated in the following list. In the list, "split" refers to the cross-validation split to which a sentence belongs, and "batch" to the work package the sentence belongs to. Indexes to the original corpus are strings consisting of a filename, like comments2008c.vrt, a space character, and a sentence id number in the file.

The additional annotations, new in this release, are in columns 6-14. In each case, only some sentences were re-annotated, and missing values are indicated by empty fields.

Columns 6-8 contain annotations for 1000 randomly selected sentences done by author A, author B, and author C respectively. Annotations are -1, 0 or 1.

Columns 9-11 contain annotations for 505 sentences where there was a strong disagreement between the original annotators, ie. both positive and negative annotations were given. The annotators are again author A, author B and author C, and annotations are again -1, 0 or 1.

Columns 12-14 contain annotations for 100 random sentences each from those sentences which had a derived score (column 5) of 1, 2, 3, 4, and 5, for a total of 500 sentences. Annotations are 1-5, and annotators are as in the previous case.


Column	Column name				Range / data type
1 	A sentiment				[-1, 1]
2 	B sentiment				[-1, 1]
3 	C sentiment				[-1, 1]
4 	majority value				[-1, 1]
5 	derived value				[1, 5]
6       Author A random sentence sentiment      [-1, 1] 
7       Author B random sentence sentiment      [-1, 1]
8       Author C random sentence sentiment      [-1, 1]
9       Author A strong disagree sentiment      [-1, 1]
10      Author B strong disagree sentiment      [-1, 1]
11      Author C strong disagree sentiment      [-1, 1]
12      Author A derived score sentiment        [1, 5]
13      Author B derived score sentiment        [1, 5]
14      Author C derived score sentiment        [1, 5]
15 	pre-annotated sentiment smiley		[-1, 1]
16 	pre-annotated sentiment product review	[-1, 1]
17 	split # 				[1, 20]
18 	batch # 				[1,9]
19 	index in original corpus		Filename & sentence id
20 	sentence text				Raw string
