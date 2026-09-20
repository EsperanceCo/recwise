{
  description = "Recwise -- offline bank reconciliation for accountants.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;

      # PolyForm Internal Use 1.0.0 has no stock nixpkgs license id and is
      # not OSI open source (see CLAUDE.md/README), so this is marked
      # unfree rather than left implicit -- building it needs
      # NIXPKGS_ALLOW_UNFREE=1, same as any other unfree nixpkgs package.
      recwiseLicense = {
        fullName = "PolyForm Internal Use License 1.0.0";
        url = "https://polyformproject.org/licenses/internal-use/1.0.0/";
        free = false;
      };
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfreePredicate = pkg: (pkg.meta.license or null) == recwiseLicense;
          };
          python = pkgs.python311;
        in
        {
          default = python.pkgs.buildPythonApplication {
            pname = "recwise";
            # Keep in sync with [project].version in pyproject.toml.
            version = "0.1.0";
            pyproject = true;
            src = ./.;

            build-system = [ python.pkgs.hatchling ];

            # Versions here follow whatever nixpkgs-unstable currently
            # carries, not the exact pins in pyproject.toml/
            # requirements-dev.lock -- Nix resolves the whole dependency
            # graph itself, and hand-pinning every transitive dependency
            # (numpy, werkzeug, rich, ...) to match those exact pins isn't
            # done here. If that drift ever causes a real behavior
            # difference, pin via an override in this derivation.
            dependencies = with python.pkgs; [
              pandas
              openpyxl
              flask
              textual
            ];

            # This packages the app for running, not for its own test
            # suite -- `nix develop` (see devShells below) is how you'd
            # run pytest/ruff/mypy/bandit against a checkout.
            doCheck = false;

            meta = {
              description = "Offline bank reconciliation for accountants.";
              homepage = "https://github.com/EsperanceCo/recwise";
              license = recwiseLicense;
              mainProgram = "recwise-app";
              platforms = pkgs.lib.platforms.unix;
            };
          };
        }
      );

      apps = forAllSystems (
        system:
        let
          pkg = self.packages.${system}.default;
          mkApp = name: {
            type = "app";
            program = "${pkg}/bin/${name}";
          };
        in
        {
          default = mkApp "recwise-app";
          recwise-app = mkApp "recwise-app";
          recwise-review = mkApp "recwise-review";
          recwise-tui = mkApp "recwise-tui";
          recwise-reconcile = mkApp "recwise-reconcile";
          recwise-audit = mkApp "recwise-audit";
          recwise-synth = mkApp "recwise-synth";
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfreePredicate = pkg: (pkg.meta.license or null) == recwiseLicense;
          };
          python = pkgs.python311;
          pythonEnv = python.withPackages (
            ps: with ps; [
              pandas
              openpyxl
              flask
              textual
              pytest
              hypothesis
              pandas-stubs
            ]
          );
        in
        {
          default = pkgs.mkShell {
            packages = [
              pythonEnv
              pkgs.ruff
              pkgs.mypy
              pkgs.bandit
            ];
          };
        }
      );
    };
}
