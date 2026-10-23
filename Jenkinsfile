#!/usr/bin/env groovy
/*
 * Dazah Jenkins CI/CD reference pipeline.
 *
 * This file is intentionally not used by GitHub Actions. It is a declarative
 * pipeline template for the single-host production topology described in
 * docs/runbooks/jenkins-ci-cd.md. Validate it in a staging Jenkins before
 * enabling automatic production deployment.
 *
 * Design rules:
 *   - PR builds must run on an untrusted agent without production credentials.
 *   - The release job must load this Jenkinsfile from main, not from a PR.
 *   - Production deployment delegates to deploy-production-remote.sh through
 *     scripts/jenkins/deploy-release.sh; Jenkins never runs alembic or compose
 *     against production directly.
 *   - A failed deployment is never automatically retried or rolled back.
 */

def isMainBranch() {
  def branch = env.BRANCH_NAME ?: env.GIT_BRANCH ?: ''
  return branch == 'main' || branch == 'origin/main'
}

def isRollback() {
  return params.PIPELINE_MODE == 'rollback'
}

def notifyFeishu(String status) {
  if (!params.FEISHU_NOTIFY) {
    return
  }
  try {
    withCredentials([string(credentialsId: 'dazah-feishu-webhook', variable: 'FEISHU_WEBHOOK')]) {
      withEnv([
        "MSG=[Dazah] ${env.JOB_NAME} #${env.BUILD_NUMBER} ${status} " +
          "version=${env.DAZAH_VERSION ?: '-'} " +
          "branch=${env.BRANCH_NAME ?: env.GIT_BRANCH ?: '-'}"
      ]) {
        sh '''
          payload=$(python3 -c 'import json,os; print(json.dumps({"msg_type":"text","content":{"text":os.environ["MSG"]}}))')
          curl -fsS --max-time 10 -H "Content-Type: application/json" -d "$payload" "$FEISHU_WEBHOOK" >/dev/null
        '''
      }
    }
  } catch (Exception exc) {
    echo "Feishu notification failed: ${exc.message}"
  }
}

def runDeployAction(String action, List<String> environment) {
  withEnv(environment) {
    if (params.DEPLOY_MODE == 'ssh') {
      sshagent(credentials: ['dazah-deploy-ssh']) {
        sh "bash scripts/jenkins/deploy-release.sh ${action}"
      }
    } else {
      sh "bash scripts/jenkins/deploy-release.sh ${action}"
    }
  }
}

pipeline {
  agent { label 'dazah-linux' }

  options {
    timestamps()
    timeout(time: 12, unit: 'HOURS')
    buildDiscarder(logRotator(numToKeepStr: '40', artifactNumToKeepStr: '10'))
    disableConcurrentBuilds()
    skipDefaultCheckout(true)
  }

  triggers {
    // Remove this trigger when a GitHub webhook is reachable. A LAN-only
    // Jenkins cannot receive GitHub webhooks, so polling is the fallback.
    pollSCM('H/5 * * * *')
  }

  parameters {
    choice(
      name: 'PIPELINE_MODE',
      choices: ['auto', 'ci-only', 'release', 'rollback'],
      description: 'auto: CI, build/deploy when DEPLOY=true; ci-only: CI only; release: build release; rollback: rollback only'
    )
    booleanParam(name: 'RUN_FULL_CI', defaultValue: false, description: 'Run all CI scopes even when change detection says otherwise')
    booleanParam(name: 'RUN_E2E', defaultValue: false, description: 'Run stable Playwright E2E after the frontend build')
    booleanParam(name: 'DEPLOY', defaultValue: false, description: 'Deploy the newly built release to production after approval')
    booleanParam(name: 'ALLOW_OUTSIDE_WINDOW', defaultValue: false, description: 'Allow deployment outside 02:00-04:30 Asia/Shanghai')
    string(name: 'NOTICE_SECONDS', defaultValue: '180', description: 'Maintenance notice in seconds (0-3600)')
    string(name: 'RELEASE_VERSION', defaultValue: '', description: 'Optional explicit immutable version; empty uses YYYYMMDD-<7sha>')
    string(name: 'ROLLBACK_VERSION', defaultValue: '', description: 'Version to restore when PIPELINE_MODE=rollback')
    string(name: 'PUBLIC_HOST', defaultValue: '192.168.40.251', description: 'Production host name or IP rendered into nginx.default.conf')
    choice(name: 'DEPLOY_MODE', choices: ['ssh', 'local'], description: 'ssh: agent connects to production; local: run on the production host')
    string(name: 'DEPLOY_HOST', defaultValue: '192.168.40.251', description: 'Production SSH host')
    string(name: 'DEPLOY_USER', defaultValue: 'livzon', description: 'Production SSH user allowed to run the deploy helper')
    booleanParam(name: 'PREDEPLOY_BACKUP', defaultValue: true, description: 'Take a verified online backup before deploying')
    booleanParam(name: 'CLEAN_WORKSPACE', defaultValue: true, description: 'Delete the workspace at the end of the build')
    booleanParam(name: 'FEISHU_NOTIFY', defaultValue: false, description: 'Send build result to the configured Feishu webhook')
  }

  environment {
    CI = 'true'
    TZ = 'Asia/Shanghai'
    NODE_OPTIONS = '--max-old-space-size=4096'
    PYTHONDONTWRITEBYTECODE = '1'
  }

  stages {
    stage('Checkout') {
      steps {
        deleteDir()
        checkout scm
        script {
          env.GIT_COMMIT_FULL = sh(returnStdout: true, script: 'git rev-parse HEAD').trim()
          env.GIT_SHORT = sh(returnStdout: true, script: 'git rev-parse --short=7 HEAD').trim()
          env.WORKSPACE_BRANCH = env.BRANCH_NAME ?: env.GIT_BRANCH ?: ''
          sh '''
            set -euo pipefail
            if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
              echo "Tracked files changed during checkout:" >&2
              git status --short --untracked-files=no >&2
              exit 1
            fi
          '''
          echo "Checked out ${env.GIT_COMMIT_FULL} on ${env.WORKSPACE_BRANCH}"
        }
      }
    }

    stage('Change Scope') {
      steps {
        script {
          sh '''
            set -euo pipefail
            git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main

            if [ -n "${CHANGE_TARGET:-}" ] && git rev-parse --verify "origin/${CHANGE_TARGET}" >/dev/null 2>&1; then
              BASE=$(git merge-base "origin/${CHANGE_TARGET}" HEAD)
            elif [ "${BRANCH_NAME:-}" = "main" ] || [ "${GIT_BRANCH:-}" = "origin/main" ]; then
              BASE=$(git rev-parse HEAD^ 2>/dev/null || git rev-list --max-parents=0 HEAD)
            else
              BASE=$(git merge-base origin/main HEAD)
            fi

            printf '%s\n' "$BASE" > .ci-base-sha
            CI_BASE_SHA="$BASE" CI_HEAD_SHA="$(git rev-parse HEAD)" \
              python3 .github/scripts/change_scope.py > scope.json
          '''
          env.CI_BASE_SHA = readFile('.ci-base-sha').trim()
          env.CI_HEAD_SHA = sh(returnStdout: true, script: 'git rev-parse HEAD').trim()
          def scope = readJSON file: 'scope.json'
          env.FRONTEND_CHANGED = scope.frontend_changed.toString()
          env.BACKEND_CHANGED = scope.backend_changed.toString()
          env.HERMES_CHANGED = scope.hermes_changed.toString()
          env.DOCKER_CHANGED = scope.docker_changed.toString()
          env.SHARED_CHANGED = scope.shared_changed.toString()
          env.DOCS_ONLY = scope.docs_only.toString()
          env.IS_MAIN = isMainBranch().toString()
          if (isRollback() && !isMainBranch()) {
            error('PIPELINE_MODE=rollback is only allowed on main')
          }
          if (params.DEPLOY && !isMainBranch()) {
            error('DEPLOY=true is only allowed on main')
          }
          if (params.PIPELINE_MODE == 'release' && !isMainBranch()) {
            error('PIPELINE_MODE=release is only allowed on main')
          }
          echo "Change scope: ${scope}"
        }
      }
    }

    stage('Repository Policy') {
      when {
        expression { !isRollback() }
      }
      steps {
        sh 'python3 scripts/check-agent-instruction-bridges.py'
        sh '''
          set -euo pipefail
          if [ "${DOCS_ONLY}" = "true" ] && [ "${IS_MAIN}" != "true" ]; then
            echo "Docs-only change; test-impact check skipped."
          else
            python3 scripts/check-test-impact.py --base "$CI_BASE_SHA" --head HEAD
          fi
        '''
      }
    }

    stage('Quality Gates') {
      failFast true
      parallel {
        stage('Backend Quality') {
          when {
            expression {
              !isRollback() && (env.BACKEND_CHANGED == 'true' || env.SHARED_CHANGED == 'true' || params.RUN_FULL_CI)
            }
          }
          steps {
            sh 'bash dazah-backend/scripts/ci.sh quality'
          }
        }

        stage('Frontend Quality') {
          when {
            expression {
              !isRollback() && (env.FRONTEND_CHANGED == 'true' || env.SHARED_CHANGED == 'true' || params.RUN_FULL_CI)
            }
          }
          steps {
            withEnv([
              "COVERAGE_BASE_SHA=${env.CI_BASE_SHA}",
              "COVERAGE_HEAD_SHA=${env.CI_HEAD_SHA}",
              "API_BASE_URL=http://127.0.0.1:4100"
            ]) {
              sh 'bash dazah-frontend/scripts/ci.sh quality'
              sh 'cd dazah-frontend && pnpm test:build'
            }
          }
        }

        stage('Hermes Quality') {
          when {
            expression {
              !isRollback() && (env.HERMES_CHANGED == 'true' || env.SHARED_CHANGED == 'true' || params.RUN_FULL_CI)
            }
          }
          steps {
            sh 'bash Hermes-Lite/scripts/ci.sh'
          }
        }
      }
    }

    stage('Backend Integration') {
      when {
        expression {
          !isRollback() && (env.BACKEND_CHANGED == 'true' || env.SHARED_CHANGED == 'true' || params.RUN_FULL_CI)
        }
      }
      steps {
        script {
          lock(resource: 'dazah-ci-services') {
            try {
              sh '''
                set -euo pipefail
                docker rm -f dazah-ci-pg dazah-ci-redis >/dev/null 2>&1 || true
                docker network create dazah-ci-net >/dev/null 2>&1 || true

                docker run -d --name dazah-ci-pg \
                  --network dazah-ci-net \
                  --publish 127.0.0.1:55432:5432 \
                  --env POSTGRES_USER=dazah_ci \
                  --env POSTGRES_PASSWORD=dazah_ci_test \
                  --env POSTGRES_DB=dazah_ci_test \
                  --env POSTGRES_INITDB_ARGS="-c max_connections=300 -c idle_in_transaction_session_timeout=60000 -c idle_session_timeout=180000" \
                  --health-cmd "pg_isready -U dazah_ci -d dazah_ci_test" \
                  --health-interval 2s --health-timeout 5s --health-retries 30 \
                  postgres:17

                docker run -d --name dazah-ci-redis \
                  --network dazah-ci-net \
                  --publish 127.0.0.1:56379:6379 \
                  --health-cmd "redis-cli ping" \
                  --health-interval 2s --health-timeout 5s --health-retries 30 \
                  redis:8-alpine

                for container in dazah-ci-pg dazah-ci-redis; do
                  for attempt in $(seq 1 30); do
                    status=$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || true)
                    if [ "$status" = "healthy" ]; then
                      break
                    fi
                    if [ "$status" = "unhealthy" ] || [ "$attempt" -eq 30 ]; then
                      docker logs "$container"
                      exit 1
                    fi
                    sleep 2
                  done
                done
              '''
              withEnv([
                'APP_ENV=test',
                'PGHOST=127.0.0.1',
                'PGPORT=55432',
                'PGUSER=dazah_ci',
                'PGPASSWORD=dazah_ci_test',
                'PGDATABASE=dazah_ci_test',
                'DATABASE_URL=postgresql+asyncpg://dazah_ci:dazah_ci_test@127.0.0.1:55432/dazah_ci_test',
                'TEST_DATABASE_URL=postgresql+asyncpg://dazah_ci:dazah_ci_test@127.0.0.1:55432/dazah_ci_test',
                'REDIS_URL=redis://127.0.0.1:56379/0',
                'MAINTENANCE_TEST_REDIS_URL=redis://127.0.0.1:56379/15',
                'SECRET_KEY=ci-only-secret-key',
                'ENCRYPTION_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=',
                'FRONTEND_URL=http://localhost:3000',
                'AGENT_TOOL_TOKEN=ci-agent-tool-token',
                'FEISHU_WS_ENABLED=false',
                'EQUIPMENT_FEISHU_WS_ENABLED=false',
                'LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=false',
                'LIVZON_FEISHU_EVENT_WS_ENABLED=false',
                'MINIO_ENABLED=false',
                "COVERAGE_BASE_SHA=${env.CI_BASE_SHA}",
                "COVERAGE_HEAD_SHA=${env.CI_HEAD_SHA}",
                "CI_BASE_SHA=${env.CI_BASE_SHA}",
                "CI_HEAD_SHA=${env.CI_HEAD_SHA}"
              ]) {
                sh 'bash dazah-backend/scripts/ci.sh integration'
              }
            } finally {
              sh '''
                docker rm -f dazah-ci-pg dazah-ci-redis >/dev/null 2>&1 || true
                docker network rm dazah-ci-net >/dev/null 2>&1 || true
              '''
            }
          }
        }
      }
    }

    stage('Frontend Build') {
      when {
        expression {
          !isRollback() && (env.FRONTEND_CHANGED == 'true' || env.SHARED_CHANGED == 'true' || params.RUN_FULL_CI)
        }
      }
      steps {
        withEnv(['API_BASE_URL=http://127.0.0.1:4100']) {
          sh 'bash dazah-frontend/scripts/ci.sh build'
        }
      }
    }

    stage('Frontend E2E') {
      when {
        expression {
          !isRollback() && params.RUN_E2E &&
            (env.FRONTEND_CHANGED == 'true' || env.SHARED_CHANGED == 'true' || params.RUN_FULL_CI)
        }
      }
      steps {
        withEnv(['API_BASE_URL=http://127.0.0.1:4100']) {
          sh 'bash dazah-frontend/scripts/ci.sh e2e'
        }
      }
    }

    stage('Build Release') {
      when {
        expression {
          !isRollback() &&
            isMainBranch() &&
            params.PIPELINE_MODE != 'ci-only' &&
            (params.DEPLOY || params.PIPELINE_MODE == 'release')
        }
      }
      steps {
        script {
          def version = params.RELEASE_VERSION?.trim()
          if (!version) {
            version = sh(returnStdout: true, script: 'TZ=Asia/Shanghai date +%Y%m%d').trim() + '-' + env.GIT_SHORT
          }
          env.DAZAH_VERSION = version
          env.RELEASE_DIR = "${env.WORKSPACE}/release/${version}"
          withEnv([
            "PUBLIC_HOST=${params.PUBLIC_HOST}",
            "RELEASE_VERSION=${version}"
          ]) {
            sh '''
              set -euo pipefail
              bash scripts/jenkins/build-release.sh \
                --version "$RELEASE_VERSION" \
                --public-host "$PUBLIC_HOST" \
                --release-root "$WORKSPACE/release"
            '''
          }
          sh 'test -f "$RELEASE_DIR/manifest.json"'
          currentBuild.description = "Release ${env.DAZAH_VERSION}"
        }
      }
    }

    stage('Deploy Production') {
      when {
        expression {
          params.DEPLOY && !isRollback() && isMainBranch() &&
            params.PIPELINE_MODE != 'ci-only' && env.DAZAH_VERSION
        }
      }
      steps {
        script {
          timeout(time: 8, unit: 'HOURS') {
            env.DEPLOY_APPROVER = input(
              message: "Deploy ${env.DAZAH_VERSION} to production at ${params.DEPLOY_HOST}?",
              ok: '部署',
              submitter: 'dazah-approvers',
              submitterParameter: 'APPROVER'
            )
          }
          echo "Deployment approved by ${env.DEPLOY_APPROVER}"

          withEnv(["ALLOW_OUTSIDE_WINDOW=${params.ALLOW_OUTSIDE_WINDOW}"]) {
            sh '''
              set -euo pipefail
              hour=$((10#$(TZ=Asia/Shanghai date +%H%M)))
              if [ "$hour" -lt 200 ] || [ "$hour" -ge 430 ]; then
                if [ "$ALLOW_OUTSIDE_WINDOW" != "true" ]; then
                  echo "ERROR: outside the 02:00-04:30 Asia/Shanghai deployment window." >&2
                  echo "Set ALLOW_OUTSIDE_WINDOW=true and obtain explicit approval for a hotfix." >&2
                  exit 1
                fi
                echo "WARNING: deploying outside the standard window (explicit override)."
              fi
            '''
          }

          def deployEnv = [
            "VERSION=${env.DAZAH_VERSION}",
            "RELEASE_DIR=${env.RELEASE_DIR}",
            "NOTICE_SECONDS=${params.NOTICE_SECONDS}",
            "DEPLOY_MODE=${params.DEPLOY_MODE}",
            "DEPLOY_HOST=${params.DEPLOY_HOST}",
            "DEPLOY_USER=${params.DEPLOY_USER}",
            "PREDEPLOY_BACKUP=${params.PREDEPLOY_BACKUP ? '1' : '0'}"
          ]

          lock(resource: 'dazah-production-deploy') {
            runDeployAction('deploy', deployEnv)
            sleep(time: 5, unit: 'MINUTES')
            runDeployAction('verify', deployEnv)
          }
          currentBuild.description = "Deployed ${env.DAZAH_VERSION}"
        }
      }
    }

    stage('Rollback Production') {
      when {
        expression { isRollback() && isMainBranch() }
      }
      steps {
        script {
          def target = params.ROLLBACK_VERSION?.trim()
          if (!target) {
            error('ROLLBACK_VERSION is required when PIPELINE_MODE=rollback')
          }
          timeout(time: 2, unit: 'HOURS') {
            env.ROLLBACK_APPROVER = input(
              message: "Roll back production to ${target}? Database migrations are not reverted.",
              ok: '回滚',
              submitter: 'dazah-approvers',
              submitterParameter: 'APPROVER'
            )
          }
          echo "Rollback approved by ${env.ROLLBACK_APPROVER}"

          lock(resource: 'dazah-production-deploy') {
            runDeployAction('rollback', [
              "VERSION=${target}",
              "NOTICE_SECONDS=${params.NOTICE_SECONDS}",
              "DEPLOY_MODE=${params.DEPLOY_MODE}",
              "DEPLOY_HOST=${params.DEPLOY_HOST}",
              "DEPLOY_USER=${params.DEPLOY_USER}",
              "PREDEPLOY_BACKUP=0"
            ])
          }
          currentBuild.description = "Rolled back to ${target}"
        }
      }
    }
  }

  post {
    always {
      junit allowEmptyResults: true, testResults: '**/.pytest_cache/*junit.xml'
      archiveArtifacts(
        artifacts: 'scope.json, release/*/manifest.json, release/*/*.sha256, dazah-backend/coverage.xml, dazah-frontend/coverage/cobertura-coverage.xml',
        allowEmptyArchive: true
      )
    }
    success {
      script { notifyFeishu('SUCCESS') }
    }
    unstable {
      script { notifyFeishu('UNSTABLE') }
    }
    failure {
      script { notifyFeishu('FAILURE') }
    }
    cleanup {
      script {
        if (params.CLEAN_WORKSPACE) {
          deleteDir()
        }
      }
    }
  }
}
