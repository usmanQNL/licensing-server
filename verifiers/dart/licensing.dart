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

// ---- Locating the license file (.env: <APP_NAME>_LICENSE_FILE) ----
// Pure string helpers, so they work in Flutter too. Read the variable from your app's .env
// (for example with flutter_dotenv) or Platform.environment. It holds the full path; resolve a relative
// value against the app root. Unset: use defaultLicenseFile in the current working directory.

/// Name of the .env variable that holds the license file's location, e.g. 'QuellDAP' -> 'QUELLDAP_LICENSE_FILE'.
String licenseFileEnvVar(String appName) {
  var stem = appName.toUpperCase().replaceAll(RegExp(r'[^A-Z0-9]+'), '_').replaceAll(RegExp(r'^_+|_+$'), '');
  if (stem.isEmpty) stem = 'APP';
  if (RegExp(r'^[0-9]').hasMatch(stem)) stem = 'APP_$stem';
  return '${stem}_LICENSE_FILE';
}

/// Used when <APP>_LICENSE_FILE is not set: license.json in the current working directory.
const defaultLicenseFile = 'license.json';

/// KEY=VALUE pairs from the text of a .env file. Comments and blank lines are skipped.
Map<String, String> parseDotenv(String text) {
  final values = <String, String>{};
  for (var line in const LineSplitter().convert(text)) {
    line = line.trim();
    if (line.isEmpty || line.startsWith('#') || !line.contains('=')) continue;
    var key = line.substring(0, line.indexOf('=')).trim();
    if (key.startsWith('export ')) key = key.substring(7).trim();
    var value = line.substring(line.indexOf('=') + 1).trim();
    if (value.length >= 2 && value[0] == value[value.length - 1] && (value[0] == '"' || value[0] == "'")) {
      value = value.substring(1, value.length - 1);
    }
    values[key] = value;
  }
  return values;
}

// ---- issuer_url and the license cache (.env: <APP_NAME>_LICENSE_CACHE) ----
// This verifier checks license files only. If your Dart or Flutter app runs the online check,
// follow SPEC.md section 5: send it to the license's issuer_url, keep the cache file below,
// and port check_online_reply from the Python or Node verifier, including the issuer match.

/// Name of the .env variable that holds the license cache file's location, e.g. 'QuellDAP' -> 'QUELLDAP_LICENSE_CACHE'.
String licenseCacheEnvVar(String appName) {
  final fileVar = licenseFileEnvVar(appName);
  return '${fileVar.substring(0, fileVar.length - '_LICENSE_FILE'.length)}_LICENSE_CACHE';
}

/// The cache file used when <APP>_LICENSE_CACHE is unset: next to the license file, named after it.
/// license.json -> license.cache.json, LIC-1.license.json -> LIC-1.license.cache.json.
String defaultCacheFile(String licenseFile) {
  final cut = licenseFile.lastIndexOf(RegExp(r'[/\\]')) + 1;
  final folder = licenseFile.substring(0, cut);
  final name = licenseFile.substring(cut);
  final stem = name.toLowerCase().endsWith('.json') ? name.substring(0, name.length - 5) : name;
  return '$folder$stem.cache.json';
}

/// issuer_url must be https. http is accepted only for localhost, for local tests.
bool validIssuerUrl(String? url) {
  if (url == null || url.length > 2048) return false;
  final u = Uri.tryParse(url);
  if (u == null) return false;
  if (u.scheme == 'https') return u.host.isNotEmpty;
  return u.scheme == 'http' && const ['localhost', '127.0.0.1', '::1'].contains(u.host);
}

/// True unless both sides name an issuer and they differ. Licenses and replies from before
/// issuer_url existed have none, and still match.
bool sameIssuer(String? licenseIssuer, String? replyIssuer) {
  if (licenseIssuer == null || licenseIssuer.isEmpty || replyIssuer == null || replyIssuer.isEmpty) return true;
  String norm(String u) => u.replaceAll(RegExp(r'/+$'), '');
  return norm(licenseIssuer) == norm(replyIssuer);
}
