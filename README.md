## AWS Python Lambda SAM Builder

Like https://github.com/serverless/serverless-python-requirements but much simpler and for AWS SAM.

Speeds up cross-building for x86_64 on ARM64 by using a local cache.

### Usage

Put a Makefile (SAM requires capital M and a make target that matches the logical resources name) in your lambda function top dir:

```Makefile
install-builder:
	@python -c "import aws_pylambda_sam_builder" || @pip install aws_pylambda_sam_builder

.PHONY: build-YourLambda
build-YourLambda: install-builder
	@python -m aws_pylambda_sam_builder --aws-runtime py311 --aws-architecture x86_64 --source ./ --destination $(ARTIFACTS_DIR)
```

Set your SAM config to build with Makefile:

```yaml
Resources:
  YourLambda:
    Metadata:
      BuildMethod: makefile
```

Now `sam build --build-in-source --parallel -t template.yaml YourLambda` uses per-package caching, doesn't need a container, and builds in 100ms after the first build.

### Issues
* probably not safe for concurrent builds
* can't build from source (only does binary wheels)
* requires all transitive deps to be listed in requirements.txt. I did `poetry export -f initial_requirements.txt -o requirements.txt --without-hashes` 


### New in 0.2
* Support for AWS Lambda python 3.13 environment
* File lock for concurrent builds
* Bugfix: previously, if a download failed, e.g. because no compiled package existed, a folder with the metadata hash would still be created. Then the next run would "succeed", but the dependency would not end up in the lambda zip. Current version makes sure to crash and delete the folder if downloading fails.