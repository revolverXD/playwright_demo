pipeline {
    agent {
        docker {
            image 'mcr.microsoft.com/playwright:v1.64.1-noble'
			reuseNode true
        }
    }
    environment {
        HOME = "${WORKSPACE}"
        UV_INSTALL_DIR = "${WORKSPACE}/.uv-bin"
        VIRTUAL_ENV = "${WORKSPACE}/playwright_demo/.venv"
        DEMO_DIR = "${WORKSPACE}/playwright_demo"
        VENV_BIN_PATH = "${VIRTUAL_ENV}/bin"
        PATH = "${VIRTUAL_ENV}/bin:${UV_INSTALL_DIR}:${PATH}"
        ASR_APP = "${WORKSPACE}/playwright_demo/astroid_mining"
    }
    
    stages {
        stage('Cleanup') {
            steps { 
                sh 'rm -rf playwright_demo'
            }
        }
        stage('Clone GitHub repository') {
            steps {
                sh "git clone https://github.com/revolverXD/playwright_demo"
            }
        }
        stage('Setup UV'){
            steps {
                sh 'curl -LsSf https://astral.sh/uv/install.sh | sh'
                sh '$UV_INSTALL_DIR/uv --version'
                dir('playwright_demo') {
                    sh '$UV_INSTALL_DIR/uv venv --python 3.14'
                    sh '$UV_INSTALL_DIR/uv pip install -r requirements.txt'
                    sh '$UV_INSTALL_DIR/uv pip install -r astroid_mining/requirements.txt'
                }
            }
        }
        stage('Check setup'){
            steps{
                sh '''
                whoami
                pwd
                ls -lsa $VIRTUAL_ENV/bin
                $VENV_BIN_PATH/pytest --version
                $VENV_BIN_PATH/pytest --collect-only
                $VENV_BIN_PATH/playwright --version
                $VENV_BIN_PATH/playwright install
                $UV_INSTALL_DIR/uv run python --version
                '''
            }
        }
        stage('Bring up the astroid app online'){
            steps{
                dir("$ASR_APP"){
                    sh '''
                    nohup $UV_INSTALL_DIR/uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > uvicorn.log 2>&1 &
                    timeout 30 bash -c '
                            until curl -s http://127.0.0.1:8000/docs > /dev/null 2>&1 || curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; do
                                echo "Waiting for Uvicorn to boot..."
                                sleep 1
                            done
                        ' || {
                            echo "--- Uvicorn failed to start. Logs: ---"
                            cat uvicorn.log
                            exit 1
                            }
                    '''
                }
            }
        }
        stage("test astroid webapp"){
            steps{
                dir("$DEMO_DIR"){
                    sh '$VENV_BIN_PATH/pytest -m api'
                }
                
            }
        }
    }
    post{
        always {
            sh 'pkill -f "uvicorn" || true'
        }
    }
}