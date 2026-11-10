"""Small OpenStax-shaped XML: a book with a unit, two chapters, one loose preface module."""

COLLECTION = """<col:collection xmlns="http://cnx.rice.edu/collxml" xmlns:md="http://cnx.rice.edu/mdml"
    xmlns:col="http://cnx.rice.edu/collxml">
  <col:metadata>
    <md:title>Tiny Book</md:title>
    <md:slug>tiny-book</md:slug>
    <md:language>en</md:language>
    <md:license url="http://creativecommons.org/licenses/by/4.0/">CC BY</md:license>
  </col:metadata>
  <col:content>
    <col:module document="m0"/>
    <col:subcollection>
      <md:title>Unit One</md:title>
      <col:content>
        <col:subcollection>
          <md:title>Loops</md:title>
          <col:content><col:module document="m1"/><col:module document="m2"/></col:content>
        </col:subcollection>
      </col:content>
    </col:subcollection>
    <col:subcollection>
      <md:title>Functions</md:title>
      <col:content><col:module document="m3"/></col:content>
    </col:subcollection>
  </col:content>
</col:collection>"""

ND_COLLECTION = COLLECTION.replace("licenses/by/4.0", "licenses/by-nd/4.0")

MODULE = """<document xmlns="http://cnx.rice.edu/cnxml" xmlns:m="http://www.w3.org/1998/Math/MathML">
  <title>While loops</title>
  <content>
    <para id="p0">A loop repeats code.</para>
    <section id="s1">
      <title>Learning objectives</title>
      <list id="l1">
        <item>Write a while loop.</item><item>Stop a loop with <code>break</code>.</item>
      </list>
    </section>
    <section id="s2">
      <title>The while statement</title>
      <para id="p1">The mean is <m:math>
        <m:mover><m:mi>x</m:mi><m:mo>¯</m:mo></m:mover><m:mo>=</m:mo>
        <m:mfrac><m:mrow><m:mi>a</m:mi><m:mo>+</m:mo><m:mi>b</m:mi></m:mrow><m:mn>2</m:mn></m:mfrac></m:math>
        and <m:math><m:msup><m:mi>x</m:mi><m:mn>2</m:mn></m:msup></m:math>.</para>
      <code display="block">while n &gt; 0:
    n -= 1</code>
      <note id="n1" class="checkpoint">
        <title>Check</title>
        <exercise id="e1">
          <problem><para>What does break do?</para></problem>
          <solution><para>It leaves the loop.</para></solution>
        </exercise>
        <exercise id="e2">
          <problem><para><link class="os-embed" url="#exercise/X"/></para></problem>
        </exercise>
      </note>
      <media alt="diagram"><image src="x.png"/></media>
    </section>
  </content>
  <glossary>
    <definition><term>loop</term><meaning>code that repeats</meaning></definition>
  </glossary>
</document>"""

OBJECTIVES_NOTE_MODULE = """<document xmlns="http://cnx.rice.edu/cnxml">
  <title>Introduction</title>
  <content>
    <note id="o" class="chapter-objectives"><title>Chapter Objectives</title>
      <list><item>Define a function.</item></list></note>
    <para id="p">Functions name a computation.</para>
  </content>
</document>"""
