Canary testing for Checkbox edge version: in-depth process
==========================================================

Introduction
------------

Canary testing applies on Checkbox snaps that are released through the `edge channel <https://snapcraft.io/docs/channels>`_ in the Snap Store. New versions are built daily if changes are made in the code repository.

The following sections provide a detailed walk-through of the canary testing process for the Checkbox Edge version, starting from snap building to the outcomes of the testing.

Snap build and release
-----------------------

Trigger conditions
^^^^^^^^^^^^^^^^^^
The GitHub action responsible for building the snap runs every day. However, it only triggers when the following condition is met:

At least one pull request (PR) has been merged since the last edge build.

Build workflow
^^^^^^^^^^^^^^^

To monitor the build process, or to review the configuration and logs, see `the GitHub workflow <https://github.com/canonical/checkbox/actions/workflows/checkbox-snap-daily-builds.yml>`_.

Post-build actions
^^^^^^^^^^^^^^^^^^

Once the build is successful, the snap packages are automatically pushed to the Snap Store in the edge channel. Testers and early adopters can access the latest version through edge releases.

Jenkins monitoring and validation
---------------------------------

Snap monitoring
^^^^^^^^^^^^^^^

Once the snap is published to the edge channel in the Snap Store, our Jenkins job titled ``checkbox-edge-validation-detect-new-build`` gets into action.

Monitoring job URL
^^^^^^^^^^^^^^^^^^

This Jenkins job monitors the Snap Store for the presence of the new snap using the following URL:

``https://api.snapcraft.io/v2/snaps/find?q=checkbox22&channel=edge&fields=revision&architecture=amd64``

The specific JSON path that's being monitored for changes is:

``$.results[0].revision.revision``

The job checks this path every minute for updates.

Validation and wait logic
^^^^^^^^^^^^^^^^^^^^^^^^^

Upon detecting a new snap:

1. The job verifies the presence of all other related checkbox snaps.
2. If any snap is missing, the job waits for an hour, periodically checking for its availability.
3. If the snaps are available within the waiting period, the next stage of testing is initiated.

checkbox-edge-canary-validation pipeline
----------------------------------------

Upon successful snap validation, the ``checkbox-edge-canary-validation`` pipeline begins its operation.

The :doc:`canary_pipeline` contains the groovy script implementing the pipeline.

Testing platforms and specifications
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


The pipeline concurrently runs 3 distinct jobs on different platforms:

1. **amd64 ubuntu core 22**: Utilizing machines that consume Testflinger tasks from the ``dearest team`` queue.
2. **amd64 ubuntu core 16**: Also using machines from the ``dearest team`` queue, which corresponds to generic x86_64 machines.
3. **arm64 ubuntu core 22**: Targeting machines in the ``cert-rpi4b4g`` queue, which corresponds to the Raspberry Pi4 4GB model.

The :doc:`validation_job_example` contains the Jenkins job definition for the amd64 ubuntu core 22 validation.

For a detailed look on how the job execution is carried out by all the entities in the chain,
refer to the :doc:`validation_pipeline_execution`.

Canary test plan criteria
^^^^^^^^^^^^^^^^^^^^^^^^^

The canary test plan outlines specific tests that are imperative for the new snap's validation. The pipeline's successful conclusion is contingent upon all these tests passing on each of the mentioned platforms.

Outcome and information propagation
-----------------------------------

Should the validation complete without errors, the `beta` reference in the Checkbox repository is set to point at the revision that got validated.
The `beta` branch head is then updated on GitHub.

Conclusion
----------

This canary testing process, complete from snap building to testing, ensures that every release of Checkbox in the edge channel is thoroughly vetted and stable. 


.. toctree::
   :hidden:

   canary_pipeline
   validation_pipeline_execution
   validation_job_example
