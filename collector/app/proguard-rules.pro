# kotlinx.serialization keeps its serializers via generated companions.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class **$$serializer { *; }
-keepclasseswithmembers class * {
    kotlinx.serialization.KSerializer serializer(...);
}

# Ktor picks its engine reflectively.
-keep class io.ktor.client.engine.okhttp.** { *; }
-dontwarn org.slf4j.**
