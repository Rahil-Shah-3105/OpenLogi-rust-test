use std::collections::HashMap;

use strum::IntoEnumIterator as _;
use xshell::Shell;

use super::{Action, GROUPS, Job};
use crate::commands::ci::Host;
use crate::support::fs::repo_root;

/// `ci.yml`, or `None` when this tree carries no CI metadata at all.
///
/// The Nix package builds from a source derivation that deliberately excludes
/// documentation and CI metadata — editing a workflow must not rebuild the
/// application — and it runs `cargo test` inside that sandbox. The condition is
/// the whole `.github` directory rather than the workflow file: a tree that has
/// the directory but lost `ci.yml` is drift, and still fails below.
fn workflow() -> Option<String> {
    let github = repo_root().expect("repo root").join(".github");
    if !github.is_dir() {
        return None;
    }
    let path = github.join("workflows/ci.yml");
    Some(fs_err::read_to_string(path).expect("ci.yml is readable"))
}

/// The workflow with its line continuations joined back up and every run of
/// whitespace collapsed, so a command it wraps for readability is one line
/// again.
fn workflow_commands(workflow: &str) -> String {
    workflow
        .replace("\\\n", " ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

/// `ci.yml` is the pipeline's source of truth and this runner is a copy of it.
/// A copy nothing checks is a copy that drifts.
///
/// Only the jobs whose plan does not depend on the host are compared. The
/// other five pick their invocation — or whether they can run at all — from
/// what the machine has: `shell` needs shellcheck and shfmt, `msrv` a
/// toolchain, `cargo-deny` either the binary or nix, `clippy (windows)` a
/// cross std, `wasm` the wasm32 std. Each is documented as a proxy for its CI
/// job rather than a copy of it, and `wasm` gets
/// [`wasm_checks_the_crates_ci_checks`] instead, which compares the crate list
/// rather than a plan.
#[test]
fn ci_yml_runs_what_this_runner_runs() {
	log::debug!(">>> Entering ci_yml_runs_what_this_runner_runs()");
    let Some(workflow) = workflow() else {
        return;
    };
    let commands = workflow_commands(&workflow);
	log::debug!("ci_yml_runs_what_this_runner_runs(): commands → {}", commands);
    let sh = Shell::new().expect("a shell");
    sh.change_dir(repo_root().expect("repo root"));

    for job in [
        Job::Rustfmt,
        Job::PublishClosure,
        Job::Clippy,
        Job::Rustdoc,
        Job::TestsLinux,
        Job::TestsMacos,
    ] {
        let host = *job.spec().hosts.first().expect("every job names a host");
        let plan = job.plan(&sh, host).expect("a plan");
        let Action::Run(steps) = plan.action else {
            panic!("{job:?} planned no steps for {host}");
        };
        for step in steps {
            let argv = step.argv_line();
            assert!(
                commands.contains(&argv),
                "ci.yml does not run `{argv}` for {job:?}"
            );
        }
	log::debug!("<<< Exiting ci_yml_runs_what_this_runner_runs()");
    }
}

/// The wasm job skips itself on a machine without the wasm32 std, so its plan
/// cannot be compared against `ci.yml` the way the others are. What must not
/// drift is the crate list: a crate declared portable here but absent from the
/// workflow is a crate CI never checks.
#[test]
fn wasm_checks_the_crates_ci_checks() {
	log::debug!(">>> Entering wasm_checks_the_crates_ci_checks()");
    let Some(workflow) = workflow() else {
        return;
    };
    let commands = workflow_commands(&workflow);
	log::debug!("wasm_checks_the_crates_ci_checks(): commands → {}", commands);
    for crate_name in super::steps::wasm_portable_crates() {
        assert!(
            commands.contains(&format!("-p {crate_name}")),
            "ci.yml's wasm job does not check {crate_name}"
        );
	log::debug!("<<< Exiting wasm_checks_the_crates_ci_checks()");
    }
}

/// The other direction: a job added to `ci.yml` that this runner cannot even
/// name is a job nobody can reproduce locally.
#[test]
fn every_ci_yml_job_name_resolves() {
	log::debug!(">>> Entering every_ci_yml_job_name_resolves()");
    let Some(workflow) = workflow() else {
        return;
    };
    // Job names sit at one indent level under `jobs:`; a step's `- name:` is
    // deeper and carries the dash.
    let names: Vec<&str> = workflow
        .lines()
        .filter_map(|line| line.strip_prefix("    name: "))
        .collect();
    assert!(!names.is_empty(), "found no job names in ci.yml");
    for name in names {
        assert!(
            Job::resolve(name).is_some(),
            "ci.yml has a job named {name} that `cargo xtask ci` cannot run"
        );
	log::debug!("<<< Exiting every_ci_yml_job_name_resolves()");
    }
}

#[test]
fn every_name_resolves_to_its_own_job() {
	log::debug!(">>> Entering every_name_resolves_to_its_own_job()");
    for job in Job::iter() {
        for name in job.names() {
            assert_eq!(
                Job::resolve(name).as_deref(),
                Some(&[job][..]),
                "name {name}"
            );
        }
	log::debug!("<<< Exiting every_name_resolves_to_its_own_job()");
    }
}

#[test]
fn names_are_unique_across_jobs() {
	log::debug!(">>> Entering names_are_unique_across_jobs()");
    let mut owners: HashMap<&str, Job> = HashMap::new();
    for job in Job::iter() {
        for name in job.names() {
            if let Some(other) = owners.insert(name, job) {
                panic!("name {name} is claimed by both {other:?} and {job:?}");
            }
        }
    }
    for (group, _) in GROUPS {
        assert!(
            !owners.contains_key(group),
            "group {group} also names a single job"
        );
	log::debug!("<<< Exiting names_are_unique_across_jobs()");
    }
}

#[test]
fn matrix_leg_names_resolve() {
	log::debug!(">>> Entering matrix_leg_names_resolve()");
    // What someone copies out of a CI run's job list.
    for name in [
        "MSRV (cargo check, macos-latest)",
        "MSRV (cargo check, ubuntu-latest)",
    ] {
        assert_eq!(Job::resolve(name).as_deref(), Some(&[Job::Msrv][..]));
    }
    for name in ["tests (macos, arm64)", "tests (macos, x86_64)"] {
        assert_eq!(Job::resolve(name).as_deref(), Some(&[Job::TestsMacos][..]));
	log::debug!("<<< Exiting matrix_leg_names_resolve()");
    }
}

#[test]
fn tests_names_both_test_jobs() {
	log::debug!(">>> Entering tests_names_both_test_jobs()");
    assert_eq!(
        Job::resolve("tests").as_deref(),
        Some(&[Job::TestsLinux, Job::TestsMacos][..])
	log::debug!("<<< Exiting tests_names_both_test_jobs()");
    );
}

#[test]
fn unknown_job_names_do_not_resolve() {
	log::debug!(">>> Entering unknown_job_names_do_not_resolve()");
    assert_eq!(Job::resolve("nightly"), None);
	log::debug!("<<< Exiting unknown_job_names_do_not_resolve()");
    assert_eq!(Job::resolve(""), None);
}

#[test]
fn the_default_run_is_the_ci_jobs_only() {
	log::debug!(">>> Entering the_default_run_is_the_ci_jobs_only()");
    // The focused suites are not jobs in ci.yml; a bare run must not claim
    // to have covered a pipeline job by running them.
    let default: Vec<Job> = Job::default_run().collect();
    for job in [Job::I18n, Job::Wire] {
        assert!(!default.contains(&job), "{job:?} is not a ci.yml job");
    }
    for job in Job::iter().filter(|job| ![Job::I18n, Job::Wire].contains(job)) {
        assert!(default.contains(&job), "{job:?} is a ci.yml job");
	log::debug!("<<< Exiting the_default_run_is_the_ci_jobs_only()");
    }
}

/// The host lists are what decides a skip, so they are worth stating: on a
/// `cfg!` these were only ever evaluated on the host that made them true.
#[test]
fn jobs_name_the_hosts_ci_gives_them() {
	log::debug!(">>> Entering jobs_name_the_hosts_ci_gives_them()");
    let hosts = |job: Job| job.spec().hosts.to_vec();
    assert_eq!(hosts(Job::TestsLinux), vec![Host::Linux]);
    assert_eq!(hosts(Job::TestsMacos), vec![Host::Macos]);
    // CI's msrv matrix is macos-latest + ubuntu-latest — there is no
    // Windows leg to reproduce.
    assert_eq!(hosts(Job::Msrv), vec![Host::Linux, Host::Macos]);
    // Natively on Windows, everywhere else as the cross-lint proxy.
	log::debug!("<<< Exiting jobs_name_the_hosts_ci_gives_them()");
    assert_eq!(hosts(Job::ClippyWindows), Host::ANY.to_vec());
}
