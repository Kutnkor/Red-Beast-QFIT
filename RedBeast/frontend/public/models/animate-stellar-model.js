import { Quaternion, Vector3 } from "three";
// src/three/science/models.ts
/** Relative Kepler ellipse, a=1. Orbital phase and node orientation remain illustrative. */
function keplerEllipse(meanAnomaly, eccentricity, inclinationDeg) {
	if (!Number.isFinite(meanAnomaly) || !Number.isFinite(eccentricity) || eccentricity < 0 || eccentricity >= 1 || !Number.isFinite(inclinationDeg)) throw new RangeError("Invalid orbital parameters");
	const mean = (meanAnomaly % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI);
	let eccentric = mean;
	for (let iteration = 0; iteration < 12; iteration++) eccentric -= (eccentric - eccentricity * Math.sin(eccentric) - mean) / (1 - eccentricity * Math.cos(eccentric));
	const x = Math.cos(eccentric) - eccentricity;
	const y = Math.sqrt(1 - eccentricity ** 2) * Math.sin(eccentric);
	const inclination = inclinationDeg * Math.PI / 180;
	return [
		x,
		y * Math.cos(inclination),
		y * Math.sin(inclination)
	];
}
// src/three/models/animation.ts
/** Works on both the live model and an ObjectLoader-loaded .three.json snapshot. */
function animateStellarModel(root, seconds) {
	const animation = root.userData.animation;
	if (!animation) return;
	const time = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
	const primary = root.getObjectByName("primary-body"), secondary = root.getObjectByName("secondary-body");
	const surface = primary?.getObjectByName("stellar-surface");
	const phase = animation.kind === "pulsating" ? Math.sin(time * Math.PI / 4) : 0;
	surface?.scale.setScalar(animation.radius * (1 + .055 * phase));
	if (primary && secondary) {
		const position = new Vector3(...keplerEllipse(time * .06, animation.eccentricity, animation.inclinationDeg)).multiplyScalar(animation.separation / 2);
		primary.position.copy(position).negate();
		secondary.position.copy(position);
		secondary.getObjectByName("stellar-surface")?.scale.setScalar(animation.secondaryRadius ?? 1);
	}
	root.traverse((object) => {
		const uniforms = object.material?.uniforms;
		if (!uniforms) return;
		if (uniforms.uTime) uniforms.uTime.value = time;
		if (uniforms.uThermalPhase) uniforms.uThermalPhase.value = -phase;
		if (uniforms.uStrength && uniforms.uBaseStrength) uniforms.uStrength.value = uniforms.uBaseStrength.value * (1 - .04 * phase) ** 4;
	});
}
function faceStellarModel(root, camera, pixelRatio = 1) {
	root.traverse((object) => {
		const material = object.material;
		if (material?.uniforms?.uPixelRatio) material.uniforms.uPixelRatio.value = Math.max(1, Math.min(2, pixelRatio));
		if (!["surface-outline", "solar-radius-reference"].includes(object.name) || !object.parent) return;
		object.quaternion.copy(object.parent.getWorldQuaternion(new Quaternion()).invert()).multiply(camera.getWorldQuaternion(new Quaternion()));
	});
}
export { animateStellarModel, faceStellarModel };
