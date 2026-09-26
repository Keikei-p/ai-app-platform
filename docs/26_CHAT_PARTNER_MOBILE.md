# Chat Partner + Mobile Direction

The default product surface is conversation-first.

1. User describes an app in natural language.
2. AI asks only missing material decisions.
3. AI creates/updates the project.
4. Safety, Design AI, capability checks and automated tests run.
5. User reviews the preview in the same product flow.
6. User gives corrections conversationally.
7. Corrections are recorded as development lessons and the app is regenerated/retested.
8. The platform distinguishes "generated", "completion candidate", and genuinely releasable artifacts.

Desktop is the full creation environment. Mobile clients will prioritize Web-app creation/control first, then connect to hosted/desktop workers for heavier builds. Generated mobile applications use a shared React Native/Expo source tree for Android and iOS unless a project requires native-platform specialization.
