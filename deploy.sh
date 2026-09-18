#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

AWS_PROFILE="default"
AWS_REGION="us-west-2"
MODE="full"
DESTROY=false

print_header() { echo -e "${BLUE}=== $1 ===${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

while [[ $# -gt 0 ]]; do
    case $1 in
        --profile) AWS_PROFILE="$2"; shift 2 ;;
        --region) AWS_REGION="$2"; shift 2 ;;
        --mode) MODE="$2"; shift 2 ;;
        --destroy) DESTROY=true; shift ;;
        --help)
            echo "StreamForge Deployment Script"
            echo ""
            echo "Usage: ./deploy.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --profile <profile>   AWS profile (default: default)"
            echo "  --region <region>     AWS region (default: us-west-2)"
            echo "  --mode <mode>         Deployment mode: full, backend, local (default: full)"
            echo "  --destroy             Destroy all resources"
            echo "  --help                Show this help"
            echo ""
            echo "Examples:"
            echo "  ./deploy.sh --profile sandbox2025 --region us-west-2"
            echo "  ./deploy.sh --mode local"
            echo "  ./deploy.sh --destroy --profile sandbox2025"
            exit 0
            ;;
        *) print_error "Unknown option: $1"; exit 1 ;;
    esac
done

if [ "$DESTROY" = true ]; then
    print_header "Destroying StreamForge Resources"
    print_warning "This will DELETE all StreamForge AWS resources!"

    cd infrastructure
    npx cdk destroy --all --profile "$AWS_PROFILE" --force 2>/dev/null || {
        print_warning "CDK destroy failed, using CloudFormation directly..."
        for stack in StreamForgeAnalyticsStack StreamForgeProcessingStack StreamForgeIngestionStack StreamForgeStorageStack; do
            aws cloudformation delete-stack --stack-name "$stack" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null || true
        done
        print_info "Waiting for stack deletion..."
        for stack in StreamForgeAnalyticsStack StreamForgeProcessingStack StreamForgeIngestionStack StreamForgeStorageStack; do
            aws cloudformation wait stack-delete-complete --stack-name "$stack" --profile "$AWS_PROFILE" --region "$AWS_REGION" 2>/dev/null || true
        done
    }
    cd ..

    print_success "All resources destroyed"
    print_info "Monthly cost: \$0"
    exit 0
fi

print_header "StreamForge Deployment"
echo "Profile: $AWS_PROFILE"
echo "Region: $AWS_REGION"
echo "Mode: $MODE"
echo ""

if [ "$MODE" = "local" ]; then
    print_header "Local Development Mode"
    cd dashboard
    npm install
    print_success "Dependencies installed"
    print_info "Starting dashboard at http://localhost:5173"
    npx vite
    exit 0
fi

# Deploy Backend
print_header "Step 1: Installing Infrastructure Dependencies"
cd infrastructure
npm install
print_success "Dependencies installed"

print_header "Step 2: Compiling TypeScript"
npx tsc
print_success "TypeScript compiled"

print_header "Step 3: Bootstrapping CDK"
npx cdk bootstrap --profile "$AWS_PROFILE" 2>/dev/null || print_warning "Bootstrap skipped (may already be done)"

print_header "Step 4: Deploying Backend (5-10 minutes)"
npx cdk deploy --all --profile "$AWS_PROFILE" --require-approval never --outputs-file ../cdk-outputs.json
print_success "Backend deployed"
cd ..

API_URL=$(cat cdk-outputs.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(next((v for k,v in next(iter(d.values())).items() if 'ApiUrl' in k), 'NOT_FOUND'))" 2>/dev/null || echo "CHECK_CDK_OUTPUTS")

print_success "StreamForge deployed!"
echo ""
print_info "API URL: $API_URL"
echo ""
print_info "Test: curl ${API_URL}health"

if [ "$MODE" = "full" ]; then
    print_header "Step 5: Building Frontend"
    cd dashboard
    npm install

    echo "VITE_INGESTION_API=$API_URL" > .env
    echo "VITE_ANALYTICS_API=$API_URL" >> .env

    npx vite build
    print_success "Frontend built"
    cd ..
    print_info "Frontend built in dashboard/dist/"
fi

echo ""
print_success "Deployment complete!"
echo ""
echo "Destroy: ./deploy.sh --destroy --profile $AWS_PROFILE"
