# Epistemic labels

## labels

- **Measured / ölçülen:** an observed catalogue value or a measurement on valid image data;
  include its unit, source and uncertainty when available. The UI uses white.
- **Computed / hesaplanan:** a result calculated from cited inputs, for example distance
  from parallax or a predicted position at a chosen year. The UI uses orange.
- **Representative / temsili:** a graphic chosen to explain the data, such as the enlarged
  stellar surface or the spacing of time-stack planes. Its size is not a measurement;
  use a label and a dashed boundary.
- **Assumed / varsayılan:** an explicit modelling choice when an input is unavailable,
  for example radial velocity set to zero for propagation. Use an underlined label.

These categories do not represent confidence scores. A computed result can depend on an
assumption. Missing values remain missing; they must not be silently replaced with zeros.
User marks are unverified observations, not catalogue measurements or discoveries.
