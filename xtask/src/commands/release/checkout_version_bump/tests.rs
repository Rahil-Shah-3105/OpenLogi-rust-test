use super::{Resolution, resolve};
use xshell::{Shell, cmd};

#[test]
fn existing_release_tag_skips_publishing() {
	log::debug!(">>> Entering existing_release_tag_skips_publishing()");
    let (_directory, sh) = repository("0.7.5");
    cmd!(sh, "git tag v0.7.5").run().unwrap();

	log::debug!("<<< Exiting existing_release_tag_skips_publishing()");
    assert_eq!(resolve(&sh, "0.7.5").unwrap(), Resolution::AlreadyTagged);
}

#[test]
fn release_commit_subject_wins_over_manifest_history() {
	log::debug!(">>> Entering release_commit_subject_wins_over_manifest_history()");
    let (directory, sh) = repository("0.7.4");
    write_manifest(directory.path(), "0.7.5", "");
    commit(&sh, "manual version bump");
    fs_err::write(directory.path().join("release-marker"), "release").unwrap();
    let release_sha = commit(&sh, "chore: release v0.7.5 (#750)");
	log::debug!("release_commit_subject_wins_over_manifest_history(): release_sha → {}", release_sha);

    assert_eq!(
        resolve(&sh, "0.7.5").unwrap(),
        Resolution::Commit(release_sha)
	log::debug!("<<< Exiting release_commit_subject_wins_over_manifest_history()");
    );
}

#[test]
fn manifest_history_finds_a_nonstandard_version_bump() {
	log::debug!(">>> Entering manifest_history_finds_a_nonstandard_version_bump()");
    let (directory, sh) = repository("0.7.4");
    write_manifest(directory.path(), "0.7.5", "");
    let bump_sha = commit(&sh, "manual version bump");
	log::debug!("manifest_history_finds_a_nonstandard_version_bump(): bump_sha → {}", bump_sha);
    write_manifest(directory.path(), "0.7.5", "# unrelated manifest edit\n");
    commit(&sh, "chore: edit manifest metadata");

	log::debug!("<<< Exiting manifest_history_finds_a_nonstandard_version_bump()");
    assert_eq!(resolve(&sh, "0.7.5").unwrap(), Resolution::Commit(bump_sha));
}

#[test]
fn a_missing_version_bump_is_an_error() {
	log::debug!(">>> Entering a_missing_version_bump_is_an_error()");
    let (_directory, sh) = repository("0.7.4");

    let error = resolve(&sh, "0.7.5").unwrap_err();

    assert_eq!(
        error.to_string(),
        "could not locate the version-bump commit for v0.7.5"
	log::debug!("<<< Exiting a_missing_version_bump_is_an_error()");
    );
}

fn repository(version: &str) -> (tempfile::TempDir, Shell) {
    let directory = tempfile::tempdir().unwrap();
    let sh = Shell::new().unwrap();
    sh.change_dir(directory.path());
    cmd!(sh, "git init --quiet").run().unwrap();
    cmd!(sh, "git config user.name test").run().unwrap();
    cmd!(sh, "git config user.email test@example.com")
        .run()
        .unwrap();
    write_manifest(directory.path(), version, "");
    commit(&sh, "initial version");
    (directory, sh)
}

fn write_manifest(root: &std::path::Path, version: &str, suffix: &str) {
    fs_err::write(
        root.join("Cargo.toml"),
        format!(
            "[workspace]\nmembers = []\n\n[workspace.package]\nversion = \"{version}\"\nrust-version = \"1.98\"\n{suffix}"
        ),
    )
    .unwrap();
}

fn commit(sh: &Shell, message: &str) -> String {
    cmd!(sh, "git add --all").run().unwrap();
    cmd!(sh, "git commit --quiet --message {message}")
        .run()
        .unwrap();
    cmd!(sh, "git rev-parse HEAD").read().unwrap()
}
