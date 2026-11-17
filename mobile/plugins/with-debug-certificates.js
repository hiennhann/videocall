const fs = require("node:fs/promises");
const path = require("node:path");
const {AndroidConfig, withAndroidManifest, withDangerousMod} = require("expo/config-plugins");

const resource = "videocall_network_security";
const xml = `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <debug-overrides>
        <trust-anchors>
            <certificates src="user" />
        </trust-anchors>
    </debug-overrides>
</network-security-config>
`;

module.exports = function withDebugCertificates(config) {
  config = withAndroidManifest(config, ({modResults, ...rest}) => {
    const application = AndroidConfig.Manifest.getMainApplicationOrThrow(modResults);
    application.$["android:networkSecurityConfig"] = "@xml/" + resource;
    return {...rest, modResults};
  });
  return withDangerousMod(config, ["android", async mod => {
    const directory = path.join(mod.modRequest.platformProjectRoot, "app", "src", "main", "res", "xml");
    await fs.mkdir(directory, {recursive: true});
    await fs.writeFile(path.join(directory, resource + ".xml"), xml);
    return mod;
  }]);
};
