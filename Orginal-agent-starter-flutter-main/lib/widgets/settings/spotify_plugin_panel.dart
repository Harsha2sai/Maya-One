import 'package:flutter/material.dart';

import 'connectors_panel.dart';

@Deprecated('Spotify plugin panel moved to ConnectorsPanel.')
class SpotifyPluginPanel extends StatelessWidget {
  const SpotifyPluginPanel({super.key});

  @override
  Widget build(BuildContext context) {
    return const ConnectorsPanel();
  }
}
