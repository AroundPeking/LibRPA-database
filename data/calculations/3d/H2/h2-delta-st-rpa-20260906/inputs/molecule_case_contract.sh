#!/bin/bash
case_id=${1:?case id required}
tests=/HPC/sternheimer_tests
case "$case_id" in
  h2_mol|h_atom|n2_mol|n_atom)
    source "$tests/h2_n2_coulomb_consistency_20260906/case_contract.sh" "$case_id"
    producer=$tests/h2_n2_coulomb_consistency_20260906/producer/job3257190/$case_id
    producer_job_id=3257190
    ao_potentials=$tests/h2_n2_coulomb_consistency_20260906/analytic_ao_$case_id.dat
    ;;
  li2_mol|li_atom)
    source "$tests/gth_integer_molecules_20260831/jobs/case_contract.sh" "$case_id"
    producer=$tests/li2_free_space_coulomb_20260904/producer/job3215260/$case_id
    producer_job_id=3215260
    frequency=$tests/gth_integer_molecules_20260831/diagnostic_frequency/job3185601/Li2_LiH_common_nfreq32/fixed_frequency_grid.dat
    frequency_job_id=3185601
    frequency_sha=fbbfc7bdd4e691400d6947b99a6bc4794da335ff4af983cc9a89d4748d5126a2
    nfreq=32
    orbital_effective_configuration=8s3p2d
    orbital_files=Li_gga_10au_100Ry_8s3p2d.orb
    if [[ "$case_id" = li2_mol ]]; then
      naux=556
      ao_potentials=$tests/li2_analytic_ao_delta_20260905/analytic_ao_potentials.dat
    else
      naux=278
      ao_potentials=$tests/li2_coulomb_tail_20260906/analytic_ao_potentials_li.dat
    fi
    ;;
  lih_mol|h_lmax2_atom)
    source "$tests/gth_integer_molecules_20260831/jobs/case_contract.sh" "$case_id"
    producer=$tests/molecular_isolated_ri_20260906/producer/job3267700/$case_id
    producer_job_id=3267700
    frequency=$tests/gth_integer_molecules_20260831/diagnostic_frequency/job3185601/Li2_LiH_common_nfreq32/fixed_frequency_grid.dat
    frequency_job_id=3185601
    frequency_sha=fbbfc7bdd4e691400d6947b99a6bc4794da335ff4af983cc9a89d4748d5126a2
    nfreq=32
    ao_potentials=$tests/molecular_isolated_ri_20260906/analytic_ao_$case_id.dat
    if [[ "$case_id" = lih_mol ]]; then
      naux=495
      orbital_effective_configuration=Li8s3p2d_H4s3p2d
    else
      naux=217
      orbital_effective_configuration=4s3p2d
    fi
    ;;
  *) echo "unapproved case $case_id" >&2; return 2 ;;
esac
root=$tests/molecular_isolated_ri_20260906
build_job_id=${BUILD_JOB_ID:?validated build id required}
expected_abacus_sha=${ABACUS_SHA256:?validated binary hash required}
artifact=/HPC/codex_tmp/abacus-molecular-production-20260906/artifact-$build_job_id
abacus=$artifact/abacus_3p
case "$case_id" in
  h2_mol)
    v_sha=35b3186987b037ea2f07b53d79ec67d0efd40e9022f59816b062564d144b9e35
    basis_sha=e63aa14ef277801b509b49ac53336471e67e17aa6507368b7b0bcf20feceebe1
    ao_sha=1cad790a0f309ca5701ae5073842b6e5f0e76e0234a638760ad8b593ff412d4f ;;
  h_atom)
    v_sha=6376649e81335153760db4285af721bd8743f17f587cb410f1fbbf1f55f963bb
    basis_sha=364c051e7f2dbd9a43d0aeb71780f5de8d972610ed24c946d0a417f3283ab826
    ao_sha=4c86ba2a0b902aaddcdd9b5145d86dc66205cd83ee231889f0de4d68d5802580 ;;
  n2_mol)
    v_sha=0a7e5dd7e53dcc764be23e87763257febd8391c93f25d38c6ac757ca7eaba6c8
    basis_sha=638a021ef721058a0b49c91f6a445a720917b4e88956c32f803c54cdcb5b2298
    ao_sha=8e162a02eabc8b7ff48f5e07db6ec47bc4682e6a9fcbf39fb2ee5aa012533797 ;;
  n_atom)
    v_sha=4a2f2213d3d8355b61671e9b12137fb71a7dff68fa3f76d4dff2891b9aff2e84
    basis_sha=93d60fe8edfafed46c963b3fc6389926e9ab075e1490617c932f288a4817a1a4
    ao_sha=71e99fb60b28373e3cbc1d41e78a32efda523c42430241d999ce9f67a4957fd0 ;;
  li2_mol)
    v_sha=95a0d9d959a4c69288809fd1403c633388de25aceb1f4b50bd5fbdb0173f92fe
    basis_sha=420ea2eca28d3598ce72c2f96527c5b12a9843c63235bff00a9bf613973b39eb
    ao_sha=6512a02ab116005a30102f66762c00c814dcd459adbfbf4b757187b93fa19810 ;;
  li_atom)
    v_sha=24170ffe0d995a5597adeda1f67d785b668b02a0d26a7ce4909a999ae14f704d
    basis_sha=e5c7d07ba54ef8457afdc34b8f89377ee2820c91cfca1d2f42a5daa24f62b30a
    ao_sha=25eba796fa44b14d8c7b85b1fcea25dd43615014c12e405dcd94f336c66f6650 ;;
  lih_mol)
    v_sha=e28ec6f8f6d9effa0fac68769b7064aef4345ec0d9c29995fce40e29bee87a2d
    basis_sha=721d4fcc87ffe4612568de15eb7eaeac856eb09c7c9e3cbc22026f7958246495
    ao_sha=e82edaffd1eea788852be8ce794de9af9a72251ff93e42236bf36473f3a2aeb5 ;;
  h_lmax2_atom)
    v_sha=9a7e2ec68fa1efb104aefa30943b4cb32cb522ed45a4a6cf31c530aa075e9f79
    basis_sha=b3924962c83087cf4e7e8afbef4c03f392bcf36686b61353f9aa7c8a7202a2d7
    ao_sha=7415ff05514f3b9cb2d0f84db14b9735b7166a79f6aaae06635cf65dd727f833 ;;
esac
