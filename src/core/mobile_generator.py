from __future__ import annotations
from pathlib import Path
import json
import re
from .app_spec import AppSpec
from .database import log_event

class MobileGenerator:
    """Generate one Expo/React Native codebase for Android+iOS.

    This step intentionally stops before store signing/submission. Those remain
    separate approval-gated build/release steps.
    """

    def generate(self, project_dir: Path, spec: AppSpec) -> list[Path]:
        if not any(t in spec.targets for t in ("android", "ios")):
            return []

        mobile = project_dir / "mobile"
        mobile.mkdir(exist_ok=True)
        package_suffix = (re.sub(r"[^a-z0-9]+", "", spec.slug.lower()) or "app")[:40]
        app_json = {
            "expo": {
                "name": spec.project_name,
                "slug": spec.slug[:64],
                "version": "1.0.0",
                "orientation": "portrait",
                "userInterfaceStyle": "automatic",
                "android": {"package": f"com.aiappplatform.{package_suffix}"},
                "ios": {
                    "bundleIdentifier": f"com.aiappplatform.{package_suffix}",
                    "supportsTablet": True,
                },
                "web": {"bundler": "metro"},
            }
        }
        package_json = {
            "name": spec.slug,
            "version": "1.0.0",
            "private": True,
            "main": "expo/AppEntry.js",
            "scripts": {
                "start": "expo start",
                "android": "expo start --android",
                "ios": "expo start --ios",
                "web": "expo start --web",
                "typecheck": "tsc --noEmit",
            },
            "dependencies": {
                "expo": "~57.0.0",
                "react": "19.2.3",
                "react-native": "0.86.0",
            },
            "devDependencies": {
                "@types/react": "~19.2.0",
                "typescript": "~5.9.0",
            },
        }
        files: dict[str, str] = {
            "package.json": json.dumps(package_json, ensure_ascii=False, indent=2),
            "app.json": json.dumps(app_json, ensure_ascii=False, indent=2),
            "eas.json": json.dumps(
                {"build": {"preview": {"distribution": "internal"}, "production": {}}, "submit": {"production": {}}},
                ensure_ascii=False,
                indent=2,
            ),
            "tsconfig.json": json.dumps({"extends": "expo/tsconfig.base", "compilerOptions": {"strict": True}}, indent=2),
            "App.tsx": self._app_tsx(spec),
            "README.md": (
                "# Mobile app\n\n"
                "AI App Platform generated Expo/React Native source for Android/iOS.\n"
                "Build/signing remains approval-gated until credentials and store requirements are confirmed.\n"
            ),
            "build_readiness.json": json.dumps(
                {
                    "source": "ready",
                    "typecheck": "npm run typecheck",
                    "bundle_checks": {
                        "android": "npx expo export --platform android --output-dir dist-android",
                        "ios": "npx expo export --platform ios --output-dir dist-ios",
                    },
                    "android": {
                        "debug_apk": "native prebuild + Gradle supported when Java/Android SDK are available",
                        "production_aab": "requires production signing configuration before store use",
                    },
                    "ios": {
                        "native_build": "requires macOS/Xcode or a compatible remote build service",
                        "production_ipa": "requires Apple signing credentials and provisioning",
                    },
                    "store_submission": {
                        "status": "approval_required",
                        "note": "AI App Platform does not submit to stores without explicit human approval.",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
        }
        out: list[Path] = []
        for name, content in files.items():
            path = mobile / name
            path.write_text(content, encoding="utf-8")
            out.append(path)
        log_event("generator.mobile", f"Generated Expo mobile project for {spec.targets}", spec.slug)
        return out

    def _app_tsx(self, spec: AppSpec) -> str:
        title = json.dumps(spec.project_name, ensure_ascii=False)
        summary = json.dumps(spec.summary[:180], ensure_ascii=False)
        return f'''import React, {{ useState }} from 'react';
import {{ SafeAreaView, View, Text, TextInput, Pressable, StyleSheet, ScrollView }} from 'react-native';

export default function App() {{
  const [message, setMessage] = useState('');
  return (
    <SafeAreaView style={{styles.safe}}>
      <ScrollView contentContainerStyle={{styles.page}}>
        <Text style={{styles.eyebrow}}>AI APP PLATFORM</Text>
        <Text style={{styles.title}}>{{{title}}}</Text>
        <Text style={{styles.summary}}>{{{summary}}}</Text>
        <View style={{styles.card}}>
          <Text style={{styles.h2}}>はじめる</Text>
          <TextInput
            accessibilityLabel="入力"
            style={{styles.input}}
            placeholder="入力してください"
            value={{message}}
            onChangeText={{setMessage}}
          />
          <Pressable accessibilityRole="button" style={{styles.button}} onPress={{() => setMessage(message.trim())}}>
            <Text style={{styles.buttonText}}>保存</Text>
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}}

const styles = StyleSheet.create({{
  safe: {{ flex: 1, backgroundColor: '#F7F8FC' }},
  page: {{ padding: 24, gap: 16 }},
  eyebrow: {{ fontSize: 12, fontWeight: '800', letterSpacing: 1.4, color: '#667085' }},
  title: {{ fontSize: 34, fontWeight: '800', color: '#101828' }},
  summary: {{ fontSize: 16, lineHeight: 24, color: '#475467' }},
  card: {{ backgroundColor: '#FFFFFF', padding: 20, borderRadius: 20, gap: 14 }},
  h2: {{ fontSize: 20, fontWeight: '700', color: '#101828' }},
  input: {{ minHeight: 52, borderWidth: 1, borderColor: '#D0D5DD', borderRadius: 14, paddingHorizontal: 14, fontSize: 16 }},
  button: {{ minHeight: 52, borderRadius: 14, backgroundColor: '#101828', alignItems: 'center', justifyContent: 'center' }},
  buttonText: {{ color: '#FFFFFF', fontWeight: '800', fontSize: 16 }},
}});
'''
