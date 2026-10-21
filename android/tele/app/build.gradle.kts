import java.net.URI
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

fun loadProperties(file: File) = Properties().apply { file.inputStream().use { load(it) } }

val appVersion = loadProperties(rootProject.file("version.properties"))
val house = providers.gradleProperty("house").getOrElse("http://192.168.68.10:8099").trimEnd('/')
val houseHost: String = URI(house).host ?: throw GradleException("-Phouse no es una URL: $house")
val keysDir = providers.gradleProperty("keysDir").orNull
val keys = keysDir?.let { loadProperties(file("$it/keystore.properties")) }

android {
    namespace = "ar.elroso.domotica.tele"
    compileSdk = 34

    defaultConfig {
        applicationId = "ar.elroso.domotica.tele"
        minSdk = 26
        targetSdk = 34
        versionCode = appVersion.getProperty("versionCode").toInt()
        versionName = appVersion.getProperty("versionName")
        buildConfigField("String", "HOUSE_URL", "\"$house\"")
    }

    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        if (keys != null) {
            create("release") {
                storeFile = file("$keysDir/tele-release.jks")
                storePassword = keys.getProperty("storePassword")
                keyAlias = keys.getProperty("keyAlias")
                keyPassword = keys.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

// Texto claro permitido solo para el host de la casa.
abstract class NetworkConfigTask : DefaultTask() {
    @get:Input
    abstract val host: Property<String>

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun write() {
        val xml = outputDir.get().file("xml/network_security_config.xml").asFile
        xml.parentFile.mkdirs()
        xml.writeText(
            """
            |<?xml version="1.0" encoding="utf-8"?>
            |<network-security-config>
            |    <base-config cleartextTrafficPermitted="false" />
            |    <domain-config cleartextTrafficPermitted="true">
            |        <domain includeSubdomains="false">${host.get()}</domain>
            |    </domain-config>
            |</network-security-config>
            |""".trimMargin()
        )
    }
}

val networkConfig = tasks.register<NetworkConfigTask>("networkConfig") {
    host.set(houseHost)
}

androidComponents {
    onVariants { variant ->
        variant.sources.res?.addGeneratedSourceDirectory(networkConfig, NetworkConfigTask::outputDir)
    }
}

gradle.taskGraph.whenReady {
    if (keys == null && allTasks.any { it.path == ":app:assembleRelease" }) {
        throw GradleException("El release necesita la clave: correr con -PkeysDir=<carpeta>, ver build.sh")
    }
}

dependencies {
    implementation(project(":core"))
}
