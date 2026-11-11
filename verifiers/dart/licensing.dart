// License verifier (SPEC.md sections 1 to 4) for Dart and Flutter.
//
// UNTESTED: written without a Dart SDK. Run the shared cases (verifiers/cases.json)
// with `dart test` before you ship it.
//
// Dependency (pubspec.yaml):  cryptography: ^2.7.0
import 'dart:convert';

import 'package:cryptography/cryptography.dart';

const supportedVersion = 1;
const graceDays = 14;
const modes = ['opensource', 'subscription', 'gated'];
// 'full' was merged into 'subscription'. Licenses issued as 'full' still verify.
String canonicalPlan(String name) => name == 'full' ? 'subscription' : name;

class LicenseResult {
  final bool valid;
  final String reason;
  final Map<String, dynamic> payload;
  final bool inGrace;
  LicenseResult(this.valid, this.reason, [this.payload = const {}, this.inGrace = false]);
}

/// Canonical JSON: keys sorted at every level, no whitespace (SPEC.md section 1).
String canonical(dynamic value) {
  if (value is Map) {
    final keys = value.keys.map((k) => k.toString()).toList()..sort();
    return '{${keys.map((k) => '${jsonEncode(k)}:${canonical(value[k])}').join(',')}}';
  }
  if (value is List) return '[${value.map(canonical).join(',')}]';
  return jsonEncode(value);
}

/// Reads the 32-byte Ed25519 key from an SPKI PEM block.
SimplePublicKey loadPublicKey(String pem) {
  final body = pem.split('\n').where((l) => !l.startsWith('-----')).join();
  final der = base64.decode(body);
  return SimplePublicKey(der.sublist(der.length - 32), type: KeyPairType.ed25519);
}

/// keys: a PEM string, or a map of {kid: PEM} to support key rotation.
String pickKey(dynamic keys, String? kid) {
  if (keys is String) return keys;
  final map = keys as Map<String, String>;
  if (kid == null || !map.containsKey(kid)) throw ArgumentError('no trusted key for kid $kid');
  return map[kid]!;
}

Future<bool> _verifySignature(Map<String, dynamic> doc, dynamic keys) async {
  final sig = base64Url.decode(base64Url.normalize(doc['signature'] as String));
  final key = loadPublicKey(pickKey(keys, doc['kid'] as String?));
  final signature = Signature(sig, publicKey: key);
  return Ed25519().verify(utf8.encode(canonical(doc['payload'])), signature: signature);
}

/// Never throws for bad license input.
Future<LicenseResult> verifyLicense(
  String text,
  dynamic keys,
  String mode, {
  List<String> featuresNeeded = const [],
  DateTime? now,
}) async {
  mode = canonicalPlan(mode);
  if (!modes.contains(mode)) throw ArgumentError('unknown mode: $mode');
  now ??= DateTime.now().toUtc();

  Map<String, dynamic> payload;
  try {
    final doc = jsonDecode(text) as Map<String, dynamic>;
    payload = doc['payload'] as Map<String, dynamic>;
    if (!await _verifySignature(doc, keys)) return LicenseResult(false, 'invalid or unreadable license');
  } catch (_) {
    return LicenseResult(false, 'invalid or unreadable license');
  }

  if (payload['v'] != supportedVersion) return LicenseResult(false, 'unsupported license version', payload);

  final plan = canonicalPlan('${payload['plan']}');
  if (mode != 'opensource' && plan != mode) {
    return LicenseResult(false, "license is for plan '${payload['plan']}', app is '$mode'", payload);
  }

  var inGrace = false;
  if ((mode == 'subscription' || mode == 'gated') && payload['expires_at'] != null) {
    final expires = DateTime.parse(payload['expires_at'] as String).toUtc();
    if (now.isAfter(expires)) {
      if (now.isBefore(expires.add(const Duration(days: graceDays))) ||
          now.isAtSameMomentAs(expires.add(const Duration(days: graceDays)))) {
        inGrace = true;
      } else {
        return LicenseResult(false, 'license expired', payload);
      }
    }
  }

  if (mode == 'gated') {
    final features = ((payload['features'] ?? []) as List).cast<String>().toSet();
    final missing = featuresNeeded.where((f) => !features.contains(f)).toList();
    if (missing.isNotEmpty) return LicenseResult(false, 'feature not licensed: ${missing.join(', ')}', payload);
  }

  return LicenseResult(true, inGrace ? 'in grace period' : 'valid', payload, inGrace);
}
