# Platform Adapters

Core logic must not contain platform-specific publishing logic.

## Web Adapter
- static/PWA/web app build
- deployment target adapter
- custom domain integration

## Windows Adapter
- desktop package
- EXE/MSIX packaging
- signing/publishing integration later

## Android Adapter
- SDK/toolchain detection
- APK/AAB build
- signing key isolation
- Play submission assistant later

## Apple Adapter
- shared project/source generation where possible
- macOS build worker detection
- Xcode/signing/notarization/App Store steps isolated

Apple-controlled signing/review remains an external dependency. The product automates preparation and workflow, not external approval.
