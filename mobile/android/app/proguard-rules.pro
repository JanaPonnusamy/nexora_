# Axythic release rules.
#
# Flutter's Gradle plugin supplies the engine/plugin rules. Keep runtime
# annotations because several AndroidX plugins discover annotated entry points
# after R8 optimization; everything else remains eligible for shrinking.
-keepattributes RuntimeVisibleAnnotations,RuntimeInvisibleAnnotations,AnnotationDefault
